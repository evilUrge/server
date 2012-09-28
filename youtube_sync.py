import cgi
import datetime
import logging
import re
from urlparse import urlparse

import gdata.youtube
import gdata.youtube.service
import gdata.alt.appengine

from google.appengine.api import taskqueue
from google.appengine.api import users
from google.appengine.ext import db

from models import Setting, Video, Playlist, VideoPlaylist, Topic
import request_handler

def youtube_get_video_data_dict(youtube_id):
    yt_service = gdata.youtube.service.YouTubeService()

    # Now that we run these queries from the App Engine servers, we need to 
    # explicitly specify our developer_key to avoid being lumped together w/ rest of GAE and
    # throttled by YouTube's "Too many request" quota
    yt_service.developer_key = "AI39si6ctKTnSR_Vx7o7GpkpeSZAKa6xjbZz6WySzTvKVYRDAO7NHBVwofphk82oP-OSUwIZd0pOJyNuWK8bbOlqzJc9OFozrQ"
    yt_service.client_id = "n/a"

    logging.info("trying to get info for youtube_id: %s" % youtube_id)
    try:
        video = yt_service.GetYouTubeVideoEntry(video_id=youtube_id)
    except:
        video = None
    if video:
        video_data = {"youtube_id" : youtube_id,
                      "title" : video.media.title.text.decode('utf-8'),
                      "url" : video.media.player.url.decode('utf-8'),
                      "duration" : int(video.media.duration.seconds)}

        if video.statistics:
            video_data["views"] = int(video.statistics.view_count)

        video_data["description"] = (video.media.description.text or '').decode('utf-8')
        video_data["keywords"] = (video.media.keywords.text or '').decode('utf-8')

        potential_id = video_data["title"].lower()
        potential_id = re.compile("[\W_]", re.UNICODE).sub('-', potential_id);
        potential_id = potential_id.strip("-")

        number_to_add = 0
        current_id = potential_id
        while True:
            query = Video.all()
            query.filter('readable_id=', current_id)
            if (query.get() is None): #id is unique so use it and break out
                video_data["readable_id"] = current_id
                break
            else: # id is not unique so will have to go through loop again
                number_to_add+=1
                current_id = potential_id+'-'+number_to_add                       

        return video_data

    return None


def youtube_get_video_data(video):
    data_dict = youtube_get_video_data_dict(video.youtube_id)

    if data_dict is None:
        return None

    for prop, value in data_dict.iteritems():
        setattr(video, prop, value)

    return video

class YouTubeSyncStep:
    START = 0
#    UPDATE_VIDEO_AND_PLAYLIST_DATA = 1 # Sets all VideoPlaylist.last_live_association_generation = Setting.last_youtube_sync_generation_start
#    UPDATE_VIDEO_AND_PLAYLIST_READABLE_NAMES = 2
#    COMMIT_LIVE_ASSOCIATIONS = 3 # Put entire set of video_playlists in bulk according to last_live_association_generation
#    INDEX_VIDEO_DATA = 4
#    INDEX_PLAYLIST_DATA = 5
#    REGENERATE_LIBRARY_CONTENT = 6
    UPDATE_FROM_TOPICS = 1

class YouTubeSyncStepLog(db.Model):
    step = db.IntegerProperty()
    generation = db.IntegerProperty()
    dt = db.DateTimeProperty(auto_now_add = True)

class YouTubeSync(request_handler.RequestHandler):

    def get(self):

        if self.request_bool("start", default = False):
            self.task_step(0)
            self.response.out.write("Sync started")
        else:
            latest_logs_query = YouTubeSyncStepLog.all()
            latest_logs_query.order("-dt")
            latest_logs = latest_logs_query.fetch(10)

            self.response.out.write("Latest sync logs:<br/><br/>")
            for sync_log in latest_logs:
                self.response.out.write("Step: %s, Generation: %s, Date: %s<br/>" % (sync_log.step, sync_log.generation, sync_log.dt))
            self.response.out.write("<br/><a href='/admin/youtubesync?start=1'>Start New Sync</a>")

    def post(self):
        # Protected for admins only by app.yaml so taskqueue can hit this URL
        step = self.request_int("step", default = 0)

        if step == YouTubeSyncStep.START:
            self.startYouTubeSync()
#        elif step == YouTubeSyncStep.UPDATE_VIDEO_AND_PLAYLIST_DATA:
#            self.updateVideoAndPlaylistData()
#        elif step == YouTubeSyncStep.UPDATE_VIDEO_AND_PLAYLIST_READABLE_NAMES:
#            self.updateVideoAndPlaylistReadableNames()
#        elif step == YouTubeSyncStep.COMMIT_LIVE_ASSOCIATIONS:
#            self.commitLiveAssociations()
#        elif step == YouTubeSyncStep.INDEX_VIDEO_DATA:
#            self.indexVideoData()
#        elif step == YouTubeSyncStep.INDEX_PLAYLIST_DATA:
#            self.indexPlaylistData()
#        elif step == YouTubeSyncStep.REGENERATE_LIBRARY_CONTENT:
#            self.regenerateLibraryContent()
        elif step == YouTubeSyncStep.UPDATE_FROM_TOPICS:
            self.copyTopicsToPlaylist()

        log = YouTubeSyncStepLog()
        log.step = step
        log.generation = int(Setting.last_youtube_sync_generation_start())
        log.put()

        if step < YouTubeSyncStep.UPDATE_FROM_TOPICS:
            self.task_step(step + 1)

    def task_step(self, step):
        taskqueue.add(url='/admin/youtubesync/%s' % step, queue_name='youtube-sync-queue', params={'step': step})

    def startYouTubeSync(self):
        Setting.last_youtube_sync_generation_start(int(Setting.last_youtube_sync_generation_start()) + 1)

    def updateVideoAndPlaylistData(self):
        self.response.out.write('<html>')

        yt_service = gdata.youtube.service.YouTubeService()

        # Now that we run these queries from the App Engine servers, we need to 
        # explicitly specify our developer_key to avoid being lumped together w/ rest of GAE and
        # throttled by YouTube's "Too many request" quota
        yt_service.developer_key = "AI39si6ctKTnSR_Vx7o7GpkpeSZAKa6xjbZz6WySzTvKVYRDAO7NHBVwofphk82oP-OSUwIZd0pOJyNuWK8bbOlqzJc9OFozrQ"
        yt_service.client_id = "n/a"

        video_youtube_id_dict = Video.get_dict(Video.all(), lambda video: video.youtube_id)
        video_playlist_key_dict = VideoPlaylist.get_key_dict(VideoPlaylist.all())

        association_generation = int(Setting.last_youtube_sync_generation_start())

        playlist_start_index = 1
        playlist_feed = yt_service.GetYouTubePlaylistFeed(uri='http://gdata.youtube.com/feeds/api/users/khanacademy/playlists?start-index=%s&max-results=50' % playlist_start_index)

        while len(playlist_feed.entry) > 0:

            for playlist in playlist_feed.entry:

                self.response.out.write('<p>Playlist  ' + playlist.id.text)
                playlist_id = playlist.id.text.replace('http://gdata.youtube.com/feeds/api/users/khanacademy/playlists/', '')
                playlist_uri = playlist.id.text.replace('users/khanacademy/', '')
                query = Playlist.all()
                query.filter('youtube_id =', playlist_id)
                playlist_data = query.get()
                if not playlist_data:
                    playlist_data = Playlist(youtube_id=playlist_id)
                    self.response.out.write('<p><strong>Creating Playlist: ' + playlist.title.text + '</strong>')
                playlist_data.url = playlist_uri
                playlist_data.title = playlist.title.text
                playlist_data.description = playlist.description.text

                playlist_data.tags = []
                for category in playlist.category:
                    if "tags.cat" in category.scheme:
                        playlist_data.tags.append(category.term)

                playlist_data.put()
                
                for i in range(0, 10):
                    start_index = i * 50 + 1
                    video_feed = yt_service.GetYouTubePlaylistVideoFeed(uri=playlist_uri + '?start-index=' + str(start_index) + '&max-results=50')
                    video_data_list = []

                    if len(video_feed.entry) <= 0:
                        # No more videos in playlist
                        break

                    for video in video_feed.entry:

                        video_id = cgi.parse_qs(urlparse(video.media.player.url).query)['v'][0].decode('utf-8')

                        video_data = None
                        if video_youtube_id_dict.has_key(video_id):
                            video_data = video_youtube_id_dict[video_id]
                        
                        if not video_data:
                            video_data = Video(youtube_id=video_id)
                            self.response.out.write('<p><strong>Creating Video: ' + video.media.title.text.decode('utf-8') + '</strong>')

                        video_data.title = video.media.title.text.decode('utf-8')
                        video_data.url = video.media.player.url.decode('utf-8')
                        video_data.duration = int(video.media.duration.seconds)

                        if video.statistics:
                            video_data.views = int(video.statistics.view_count)

                        if video.media.description.text is not None:
                            video_data.description = video.media.description.text.decode('utf-8')
                        else:
                            video_data.decription = ' '

                        if video.media.keywords.text:
                            video_data.keywords = video.media.keywords.text.decode('utf-8')
                        else:
                            video_data.keywords = ''

                        video_data.position = video.position
                        video_data_list.append(video_data)
                    db.put(video_data_list)

                    playlist_videos = []
                    for video_data in video_data_list:                
                        playlist_video = None
                        if video_playlist_key_dict.has_key(playlist_data.key()):
                            if video_playlist_key_dict[playlist_data.key()].has_key(video_data.key()):
                                playlist_video = video_playlist_key_dict[playlist_data.key()][video_data.key()]

                        if not playlist_video:
                            playlist_video = VideoPlaylist(playlist=playlist_data.key(), video=video_data.key())
                            self.response.out.write('<p><strong>Creating VideoPlaylist(' + playlist_data.title + ',' + video_data.title + ')</strong>')
                        else:
                            self.response.out.write('<p>Updating VideoPlaylist(' + playlist_video.playlist.title + ',' + playlist_video.video.title + ')')
                        playlist_video.last_live_association_generation = association_generation
                        playlist_video.video_position = int(video_data.position.text)
                        playlist_videos.append(playlist_video)
                    db.put(playlist_videos)

            # Check next set of playlists

            playlist_start_index += 50
            playlist_feed = yt_service.GetYouTubePlaylistFeed(uri='http://gdata.youtube.com/feeds/api/users/khanacademy/playlists?start-index=%s&max-results=50' % playlist_start_index)

    def updateVideoAndPlaylistReadableNames(self):
        # Makes sure every video and playlist has a unique "name" that can be used in URLs
        query = Video.all()
        all_videos = query.fetch(100000)
        for video in all_videos:
            potential_id = re.sub('[^a-z0-9]', '-', video.title.lower());
            potential_id = re.sub('-+$', '', potential_id)  # remove any trailing dashes (see issue 1140)
            potential_id = re.sub('^-+', '', potential_id)  # remove any leading dashes (see issue 1526)                        
            if video.readable_id == potential_id: # id is unchanged
                continue
            number_to_add = 0
            current_id = potential_id
            while True:
                query = Video.all()
                query.filter('readable_id=', current_id)
                if (query.get() is None): #id is unique so use it and break out
                    video.readable_id = current_id
                    video.put()
                    break
                else: # id is not unique so will have to go through loop again
                    number_to_add+=1
                    current_id = potential_id+'-'+number_to_add                       

    def commitLiveAssociations(self):
        association_generation = int(Setting.last_youtube_sync_generation_start())

        video_playlists_to_put = []
        for video_playlist in VideoPlaylist.all():
            live = (video_playlist.last_live_association_generation >= association_generation)
            if video_playlist.live_association != live:
                video_playlist.live_association = live
                video_playlists_to_put.append(video_playlist)

        db.put(video_playlists_to_put)

    def indexVideoData(self):
        videos = Video.all().fetch(10000)
        for video in videos:
            video.index()
            video.indexed_title_changed()

    def indexPlaylistData(self):
        playlists = Playlist.all().fetch(10000)
        for playlist in playlists:
            playlist.index()
            playlist.indexed_title_changed()

    def regenerateLibraryContent(self):
        taskqueue.add(url='/library_content', queue_name='youtube-sync-queue')

    def copyTopicsToPlaylist(self):
        topic_list = Topic.get_content_topics()

        for topic in topic_list:
            playlist = Playlist.all().filter("title =", topic.standalone_title).get()
            if playlist:
                logging.info("Copying topic " + topic.standalone_title + " to playlist.")
                child_keys = topic.child_keys
                vps = VideoPlaylist.all().filter("playlist =", playlist).order("video_position").fetch(10000)

                playlist_keys = []
                for vp in vps:
                    try:
                        playlist_keys.append(vp.video.key())
                    except db.ReferencePropertyResolveError:
                        logging.info("Found reference to missing video in VideoPlaylist!")

                topic_keys = [key for key in topic.child_keys if key.kind() == "Video"]

                if playlist_keys == topic_keys:
                    logging.info("Child keys identical. No changes will be made.")
                else:
#                    logging.info("PLAYLIST: " + repr([str(key) for key in playlist_keys]))
#                    logging.info("TOPIC:    " + repr([str(key) for key in topic_keys]))

                    logging.info("Deleting old VideoPlaylists...")
                    db.delete(vps)

                    vps = []
                    for i, child_key in enumerate(topic.child_keys):
                        if child_key.kind() == "Video":
                            vps.append(VideoPlaylist(
                                video=child_key,
                                playlist=playlist,
                                video_position=i,
                                live_association = True
                                ))

                    logging.info("Creating new VideoPlaylists...")
                    db.put(vps)
            else:
                logging.info("Playlist matching topic " + topic.standalone_title + " not found.")

