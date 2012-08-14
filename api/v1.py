import os
import datetime
import logging
from itertools import izip

from flask import request, current_app, Response

import models
import layer_cache
import templatetags # Must be imported to register template tags
from avatars import util_avatars
from badges import badges, util_badges, models_badges, profile_badges
from badges.templatetags import badge_notifications_html
from phantom_users.templatetags import login_notifications_html
from exercises import attempt_problem, make_wrong_attempt
from models import StudentList
from phantom_users.phantom_util import api_create_phantom
import notifications
from gae_bingo.gae_bingo import bingo
from autocomplete import video_title_dicts, topic_title_dicts, url_title_dicts
from goals.models import (GoalList, Goal, GoalObjective,
    GoalObjectiveAnyExerciseProficiency, GoalObjectiveAnyVideo)
import profiles.util_profile as util_profile
from profiles import class_progress_report_graph, recent_activity, suggested_activity
from common_core.models import CommonCoreMap
from youtube_sync import youtube_get_video_data_dict, youtube_get_video_data
from app import App

from api import route
from api.decorators import jsonify, jsonp, pickle, compress, decompress, etag,\
    cacheable, cache_with_key_fxn_and_param
from api.auth.decorators import oauth_required, oauth_optional, admin_required, developer_required
from api.auth.auth_util import unauthorized_response
from api.api_util import api_error_response, api_invalid_param_response, api_unauthorized_response

from google.appengine.ext import db, deferred

# add_action_results allows page-specific updatable info to be ferried along otherwise plain-jane responses
# case in point: /api/v1/user/videos/<youtube_id>/log which adds in user-specific video progress info to the
# response so that we can visibly award badges while the page silently posts log info in the background.
#
# If you're wondering how this happens, it's add_action_results has the side-effect of actually mutating
# the `obj` passed into it (but, i mean, that's what you want here)
#
# but you ask, what matter of client-side code actually takes care of doing that?
# have you seen javascript/shared-package/api.js ?
def add_action_results(obj, dict_results):

    badges_earned = []
    user_data = models.UserData.current()

    if user_data:
        dict_results["user_data"] = user_data

        dict_results["user_info_html"] = templatetags.user_info(user_data.nickname, user_data)

        user_notifications_dict = notifications.UserNotifier.pop_for_user_data(user_data)

        # Add any new badge notifications
        user_badges = user_notifications_dict["badges"]
        if len(user_badges) > 0:
            badges_dict = util_badges.all_badges_dict()

            for user_badge in user_badges:
                badge = badges_dict.get(user_badge.badge_name)

                if badge:
                    if not hasattr(badge, "user_badges"):
                        badge.user_badges = []

                    badge.user_badges.append(user_badge)
                    badge.is_owned = True
                    badges_earned.append(badge)

        if len(badges_earned) > 0:
            dict_results["badges_earned"] = badges_earned
            dict_results["badges_earned_html"] = badge_notifications_html(user_badges)

        # Add any new login notifications for phantom users
        login_notifications = user_notifications_dict["login"]
        if len(login_notifications) > 0:
            dict_results["login_notifications_html"] = login_notifications_html(login_notifications, user_data)

    if type(obj) == dict:
        obj['action_results'] = dict_results
    else:
        obj.action_results = dict_results

# Return specific user data requests from request
# IFF currently logged in user has permission to view
def get_visible_user_data_from_request(disable_coach_visibility=False,
                                       user_data=None):

    user_data = user_data or models.UserData.current()
    if not user_data:
        return None

    user_data_student = request.request_student_user_data()
    if user_data_student:
        if user_data_student.user_email == user_data.user_email:
            # if email in request is that of the current user, simply return the
            # current user_data, no need to check permission to view
            return user_data

        if (user_data.developer or
                (not disable_coach_visibility and
                (user_data_student.is_coached_by(user_data) or user_data_student.is_coached_by_coworker_of_coach(user_data)))):
            return user_data_student
        else:
            return None

    else:
        return user_data

def get_user_data_coach_from_request():
    user_data_coach = models.UserData.current()
    user_data_override = request.request_user_data("coach_email")

    if user_data_override and (user_data_coach.developer or user_data_coach.is_coworker_of(user_data_override)):
        user_data_coach = user_data_override

    return user_data_coach

def get_user_data_from_json(json, key):
    """ Return the user_data specified by a username or an email.

    Sample usage:
        get_user_data_from_json(
                {
                    'coach': '<username or email>'
                },
                'coach'
            )
    """
    if not json or not key or key not in json:
        return None

    return models.UserData.get_from_username_or_email(json[key])

@route("/api/v1/topicversion/<version_id>/topics/with_content", methods=["GET"])
@route("/api/v1/topics/with_content", methods=["GET"])
@route("/api/v1/playlists", methods=["GET"]) # missing "url" and "youtube_id" properties that they had before
@jsonp
@cache_with_key_fxn_and_param(
    "casing",
    lambda version_id = None: "api_content_topics_%s_%s" % (version_id, models.Setting.topic_tree_version()),
    layer=layer_cache.Layers.Memcache)
@jsonify
def content_topics(version_id = None):
    version = models.TopicVersion.get_by_id(version_id)
    return models.Topic.get_content_topics(version)

# private api call used only by ajax homepage ... can remove once we remake the homepage with the topic tree
@route("/api/v1/topics/library/compact", methods=["GET"])
@cacheable(caching_age=(60 * 60 * 24 * 60))
@etag(lambda: models.Setting.topic_tree_version())
@jsonp
@decompress # We compress and decompress around layer_cache so memcache never has any trouble storing the large amount of library data.
@layer_cache.cache_with_key_fxn(
    lambda: "api_topics_library_compact_%s" % models.Setting.topic_tree_version(),
    layer=layer_cache.Layers.Memcache)
@compress
@jsonify
def topics_library_compact():
    topics = models.Topic.get_filled_content_topics(types = ["Video", "Url"])

    def trimmed_item(item, topic):
        trimmed_item_dict = {}
        if item.kind() == "Video":
            trimmed_item_dict['url'] = "/video/%s?topic=%s" %(item.readable_id, topic.id)
            trimmed_item_dict['key_id'] = item.key().id()
        elif item.kind() == "Url":
            trimmed_item_dict['url'] = item.url
        trimmed_item_dict['title'] = item.title
        return trimmed_item_dict

    topic_dict = {}
    for topic in topics:
        # special cases
        if ((topic.id == "new-and-noteworthy") or 
            (topic.standalone_title == "California Standards Test: Geometry" and topic.id != "geometry-2")):
            continue

        trimmed_info = {}
        trimmed_info['id'] = topic.id
        trimmed_info['children'] = [trimmed_item(v, topic) for v in topic.children]
        topic_dict[topic.id] = trimmed_info

    return topic_dict

@route("/api/v1/topicversion/<version_id>/changelist", methods=["GET"])
@developer_required
@jsonp
@jsonify
def topic_version_change_list(version_id):
    version = models.TopicVersion.get_by_id(version_id)
    return models.VersionContentChange.all().filter("version =", version).fetch(10000)

@route("/api/v1/topicversion/<version_id>/topic/<topic_id>/videos", methods=["GET"])
@route("/api/v1/topic/<topic_id>/videos", methods=["GET"])
@route("/api/v1/playlists/<topic_id>/videos", methods=["GET"])
@jsonp
@cache_with_key_fxn_and_param(
    "casing",
    (lambda topic_id, version_id = None: "api_topic_videos_%s_%s_%s" % (topic_id, 
        version_id, 
        models.Setting.topic_tree_version())         
        if version_id is None or version_id == "default" else None),
    layer=layer_cache.Layers.Memcache)
@jsonify
def topic_videos(topic_id, version_id = None):
    version = models.TopicVersion.get_by_id(version_id)
    topic = models.Topic.get_by_id(topic_id, version)
    if topic is None: 
        topic = models.Topic.get_by_title(topic_id, version) # needed for people who were using the playlists api
        if topic is None:
            raise ValueError("Invalid topic readable_id.")
    
    videos = models.Topic.get_cached_videos_for_topic(topic, False, version)
    for i, video in enumerate(videos):
        video.position = i + 1
    return videos

@route("/api/v1/topicversion/<version_id>/topic/<topic_id>/exercises", methods=["GET"])
@route("/api/v1/topic/<topic_id>/exercises", methods=["GET"])
@route("/api/v1/playlists/<topic_id>/exercises", methods=["GET"])
@jsonp
@cache_with_key_fxn_and_param(
    "casing",
    (lambda topic_id, version_id = None: "api_topic_exercises_%s_%s_%s" % (
        topic_id, version_id, models.Setting.topic_tree_version()) 
        if version_id is None or version_id == "default" else None),
    layer=layer_cache.Layers.Memcache)
@jsonify
def topic_exercises(topic_id, version_id = None):
    version = models.TopicVersion.get_by_id(version_id)
    topic = models.Topic.get_by_id(topic_id, version)
    if topic is None: 
        topic = models.Topic.get_by_title(topic_id, version) # needed for people who were using the playlists api
        if topic is None:
            raise ValueError("Invalid topic readable_id.")
    
    exercises = topic.get_exercises()
    return exercises

@route("/api/v1/topic/<topic_id>/progress", methods=["GET"])
@oauth_optional()
@jsonp
@jsonify
def topic_progress(topic_id):
    user_data = models.UserData.current()
    if not user_data:
        user_data = models.UserData.pre_phantom()

    topic = models.Topic.get_by_id(topic_id)
    if not topic:
        raise ValueError("Invalid topic id.")

    return topic.get_user_progress(user_data)

@route("/api/v1/topicversion/<version_id>/topictree", methods=["GET"])
@route("/api/v1/topictree", methods=["GET"])
@etag(lambda version_id = None: version_id) 
@jsonp
@decompress 
@layer_cache.cache_with_key_fxn(
    (lambda version_id = None: "api_topictree_%s_%s" % (version_id, 
        models.Setting.topic_tree_version())        
        if version_id is None or version_id == "default" else None),
    layer=layer_cache.Layers.Memcache)
@compress
@jsonify
def topictree(version_id = None):
    version = models.TopicVersion.get_by_id(version_id)
    return models.Topic.get_by_id("root", version).make_tree()

@route("/api/v1/dev/topictree/<version_id>/problems", methods=["GET"])
@route("/api/v1/dev/topictree/problems", methods=["GET"])
# TODO(james) add @developer_required once Tom creates interface
@jsonp
@jsonify
def topic_tree_problems(version_id = "edit"):
    version = models.TopicVersion.get_by_id(version_id)
    
    exercises = models.Exercise.all()
    exercise_dict = dict((e.key(),e) for e in exercises)

    location_dict = {}
    duplicate_positions = list()
    changes = models.VersionContentChange.get_updated_content_dict(version)
    exercise_dict.update(changes)
    
    for exercise in [e for e in exercise_dict.values() 
                     if e.live and not e.summative]:
               
        if exercise.h_position not in location_dict:
            location_dict[exercise.h_position] = {}

        if exercise.v_position in location_dict[exercise.h_position]:
            # duplicate_positions.add(exercise)
            location_dict[exercise.h_position][exercise.v_position].append(exercise)
            duplicate_positions.append(
                location_dict[exercise.h_position][exercise.v_position])
        else:
            location_dict[exercise.h_position][exercise.v_position] = [exercise]

    problems = {
        "ExerciseVideos with topicless videos" : 
            models.ExerciseVideo.get_all_with_topicless_videos(version),
        "Exercises with colliding positions" : list(duplicate_positions)}

    return problems

@route("/api/v1/dev/topicversion/<version_id>/topic/<topic_id>/topictree", methods=["GET"])
@route("/api/v1/dev/topicversion/<version_id>/topictree", methods=["GET"])
@route("/api/v1/dev/topictree", methods=["GET"])
@developer_required
@jsonp
@decompress
@layer_cache.cache_with_key_fxn(
    (lambda version_id = None, topic_id = "root": "api_topictree_export_%s_%s" % (version_id, 
        models.Setting.topic_tree_version())        
        if version_id is None or version_id == "default" else None),
    layer=layer_cache.Layers.Memcache)
@compress
@jsonify
def topictree_export(version_id = None, topic_id = "root"):
    version = models.TopicVersion.get_by_id(version_id)
    return models.Topic.get_by_id(topic_id, version).make_tree(include_hidden=True)

@route("/api/v1/dev/topicversion/<version_id>/topic/<topic_id>/topictree", methods=["PUT"])
@route("/api/v1/dev/topicversion/<version_id>/topictree", methods=["PUT"])
@route("/api/v1/dev/topictree/init/<publish>", methods=["PUT"])
@route("/api/v1/dev/topictree", methods=["PUT"])
@developer_required
@jsonp
@jsonify
def topictree_import(version_id = "edit", topic_id="root", publish=False):
    import zlib
    import pickle
    logging.info("calling /_ah/queue/deferred_import")

    # importing the full topic tree can be too large so pickling and compressing
    deferred.defer(models.topictree_import_task, version_id, topic_id, publish,
                zlib.compress(pickle.dumps(request.json)),
                _queue = "import-queue",
                _url = "/_ah/queue/deferred_import")

@route("/api/v1/topicversion/<version_id>/search/<query>", methods=["GET"])
@jsonp
@jsonify
def topictreesearch(version_id, query):
    version = models.TopicVersion.get_by_id(version_id)
    return models.Topic.get_by_id("root", version).search_tree(query)

@route("/api/v1/topicversion/<version_id>/topic/<topic_id>", methods=["GET"])
@route("/api/v1/topic/<topic_id>", methods=["GET"])
@jsonp
@layer_cache.cache_with_key_fxn(
    (lambda topic_id, version_id = None: ("api_topic_%s_%s_%s" % (
        topic_id, 
        version_id, 
        models.Setting.topic_tree_version())
        if version_id is None or version_id == "default" else None)),
    layer=layer_cache.Layers.Memcache)
@jsonify
def topic(topic_id, version_id = None):
    version = models.TopicVersion.get_by_id(version_id)
    topic = models.Topic.get_by_id(topic_id, version)
    
    if not topic:
        return api_invalid_param_response("Could not find topic with ID " + str(topic_id))

    return topic.get_visible_data()

@route("/api/v1/topicversion/<version_id>/topic/<topic_id>", methods=["PUT"])    
@route("/api/v1/topic/<topic_id>", methods=["PUT"])
@developer_required
@oauth_optional()
@jsonp
@jsonify
def put_topic(topic_id, version_id = "edit"):
    version = models.TopicVersion.get_by_id(version_id)

    user_data = models.UserData.current()
    if not user_data:
        return api_invalid_param_response("User not logged in")

    topic_json = request.json

    topic = models.Topic.get_by_id(topic_id, version)

    if not topic:
        kwargs = dict((str(key), value) for key, value in topic_json.iteritems() if key in ['standalone_title', 'description', 'tags'])
        kwargs["version"] = version
        topic = models.Topic.insert(title = topic_json['title'], parent = None, **kwargs)
    else:
        kwargs = dict((str(key), value) for key, value in topic_json.iteritems() if key in ['id', 'title', 'standalone_title', 'description', 'tags', 'hide'])
        kwargs["version"]=version
        topic.update(**kwargs)

    return {
        "id": topic.id
    }

@route("/api/v1/topicversion/default/id", methods=["GET"])
@oauth_optional()
@jsonp
@jsonify
def get_default_topic_version_id():
    default_version = models.TopicVersion.get_default_version()
    return default_version.number

def topic_find_child(parent_id, version_id, kind, id):
    version = models.TopicVersion.get_by_id(version_id)

    parent_topic = models.Topic.get_by_id(parent_id, version)
    if not parent_topic:
        return ["Could not find topic with ID %s" % str(parent_id), None, None, None]

    if kind == "Topic":
        child = models.Topic.get_by_id(id, version)
    elif kind == "Exercise":
        child = models.Exercise.get_by_name(id, version)
    elif kind == "Video":
        child = models.Video.get_for_readable_id(id, version)
    elif kind == "Url":
        child = models.Url.get_by_id_for_version(int(id), version)
    else:
        return ["Invalid kind: %s" % kind, None, None, None]

    if not child:
        return ["Could not find a %s with ID %s " % (kind, id), None, None, None]

    return [None, child, parent_topic, version]

@route("/api/v1/topicversion/<version_id>/topic/<parent_id>/addchild", methods=["POST"])   
@route("/api/v1/topic/<parent_id>/addchild", methods=["POST"])
@developer_required
@jsonp
@jsonify
def topic_add_child(parent_id, version_id = "edit"):
    kind = request.request_string("kind")        
    id = request.request_string("id")

    [error, child, parent_topic, version] = topic_find_child(parent_id, version_id, kind, id)
    if error:
        return api_invalid_param_response(error)

    pos = request.request_int("pos", default=0)

    parent_topic.add_child(child, pos)

    return parent_topic.get_visible_data()

@route("/api/v1/topicversion/<version_id>/topic/<parent_id>/deletechild", methods=["POST"])   
@route("/api/v1/topic/<parent_id>/deletechild", methods=["POST"])
@developer_required
@jsonp
@jsonify
def topic_delete_child(parent_id, version_id = "edit"):
    
    kind = request.request_string("kind")        
    id = request.request_string("id")

    [error, child, parent_topic, version] = topic_find_child(parent_id, version_id, kind, id)
    if error:
        return api_invalid_param_response(error)

    parent_topic.delete_child(child)

    return parent_topic.get_visible_data()
  
@route("/api/v1/topicversion/<version_id>/topic/<old_parent_id>/movechild", methods=["POST"])   
@route("/api/v1/topic/<old_parent_id>/movechild", methods=["POST"])
@developer_required
@jsonp
@jsonify
def topic_move_child(old_parent_id, version_id = "edit"):
    
    kind = request.request_string("kind")        
    id = request.request_string("id")

    [error, child, old_parent_topic, version] = topic_find_child(old_parent_id, version_id, kind, id)
    if error:
        return api_invalid_param_response(error)

    new_parent_id = request.request_string("new_parent_id")
    new_parent =  models.Topic.get_by_id(new_parent_id, version)
    if not old_parent_topic:
        return api_invalid_param_response("Could not find topic with ID " + str(old_parent_id))
           
    new_parent_pos = request.request_string("new_parent_pos")

    old_parent_topic.move_child(child, new_parent, new_parent_pos)

    return True    

@route("/api/v1/topicversion/<version_id>/topic/<topic_id>/ungroup", methods=["POST"])  
@route("/api/v1/topic/<topic_id>/ungroup", methods=["POST"])
@developer_required
@jsonp
@jsonify
def topic_ungroup(topic_id, version_id = "edit"):
    version = models.TopicVersion.get_by_id(version_id)

    topic = models.Topic.get_by_id(topic_id, version)
    if not topic:
        return api_invalid_param_response("Could not find topic with ID " + str(topic_id))

    topic.ungroup()

    return True

@route("/api/v1/topicversion/<version_id>/topic/<topic_id>/children", methods=["GET"])   
@route("/api/v1/topic/<topic_id>/children", methods=["GET"])
@jsonp
@layer_cache.cache_with_key_fxn(
    (lambda topic_id, version_id = None: "api_topic_children_%s_%s_%s" % (
        topic_id, version_id, models.Setting.topic_tree_version()) 
        if version_id is None or version_id=="default" else None),
    layer=layer_cache.Layers.Memcache)
@jsonify
def topic_children(topic_id, version_id = None):
    version = models.TopicVersion.get_by_id(version_id)

    topic = models.Topic.get_by_id(topic_id, version)
    if not topic:
        return api_invalid_param_response("Could not find topic with ID " + str(topic_id))

    return db.get(topic.child_keys)

@route("/api/v1/topicversion/<version_id>/setdefault", methods=["GET"])   
@developer_required
@jsonp
@jsonify
def topic_children(version_id = None):
    version = models.TopicVersion.get_by_id(version_id)
    version.set_default_version()
    models.TopicVersion.get_edit_version() # creates a new edit version if one does not already exists
    return version
    
@route("/api/v1/topicversion/<version_id>", methods=["GET"])   
@developer_required
@jsonp
@jsonify
def topic_version(version_id = None):
    version = models.TopicVersion.get_by_id(version_id)
    return version

@route("/api/v1/topicversion/<version_id>", methods=["PUT"])
@developer_required
@jsonp
@jsonify
def topic_version(version_id = None):
    version = models.TopicVersion.get_by_id(version_id)
    
    version_json = request.json

    changed = False
    for key in ["title", "description"]: 
        if getattr(version, key) != version_json[key]:
            setattr(version, key, version_json[key])
            changed = True

    if changed:
        version.put()

    return {}

@route("/api/v1/topicversions/", methods=["GET"])   
@jsonp
@jsonify
def topic_versions():
    versions = models.TopicVersion.all().order("-number").fetch(10000)
    return versions

@route("/api/v1/topicversion/<version_id>/unused_content", methods=["GET"])   
@jsonp
@jsonify
def topic_version_unused_content(version_id = None):
    version = models.TopicVersion.get_by_id(version_id)
    return version.get_unused_content()

@route("/api/v1/topicversion/<version_id>/url/<int:url_id>", methods=["GET"])
@route("/api/v1/url/<int:url_id>", methods=["GET"])   
@jsonp
@jsonify
def get_url(url_id, version_id=None):
    version = models.TopicVersion.get_by_id(version_id) if version_id else None
    return models.Url.get_by_id_for_version(url_id, version)

@route("/api/v1/topicversion/<version_id>/url/", methods=["PUT"])
@route("/api/v1/topicversion/<version_id>/url/<int:url_id>", methods=["PUT"])
@route("/api/v1/url/", methods=["PUT"])
@route("/api/v1/url/<int:url_id>", methods=["PUT"]) 
@developer_required  
@jsonp
@jsonify
def save_url(url_id = None, version_id=None):
    version = models.TopicVersion.get_by_id(version_id)
    changeable_props = ["tags", "title", "url"]

    if url_id is None:
        return models.VersionContentChange.add_new_content(models.Url, 
                                                           version,
                                                           request.json,
                                                           changeable_props)
    else:
        url = models.Url.get_by_id_for_version(url_id, version)
        if url is None:
            return api_invalid_param_response("Could not find a Url with ID %s " % (url_id))
        return models.VersionContentChange.add_content_change(
            url, 
            version, 
            request.json,
            changeable_props)

@route("/api/v1/playlists/library", methods=["GET"])
@etag(lambda: models.Setting.topic_tree_version())
@jsonp
@decompress # We compress and decompress around layer_cache so memcache never has any trouble storing the large amount of library data.
@cache_with_key_fxn_and_param(
    "casing",
    lambda: "api_library_%s" % models.Setting.topic_tree_version(),
    layer=layer_cache.Layers.Memcache)
@compress
@jsonify
def playlists_library():
    tree = models.Topic.get_by_id("root").make_tree()
    def convert_tree(tree):
        topics = []
        for child in tree.children:
            # special cases
            if child.id == "new-and-noteworthy":
                continue
            elif child.standalone_title == "California Standards Test: Algebra I" and child.id != "algebra-i":
                child.id = "algebra-i"
            elif child.standalone_title == "California Standards Test: Geometry" and child.id != "geometry-2":
                child.id = "geometry-2"

            if child.kind() == "Topic":
                topic = {}
                topic["name"] = child.title
                videos = [] 
                
                for grandchild in child.children:
                    if grandchild.kind() == "Video" or grandchild.kind() == "Url":
                        videos.append(grandchild)

                if len(videos):
                    child.videos = videos
                    child.url = ""
                    child.youtube_id = ""
                    del child.children
                    topic["playlist"] = child
                else:
                    topic["items"] = convert_tree(child)
                
                topics.append(topic)
        return topics            

    return convert_tree(tree)

# We expose the following "fresh" route but don't publish the URL for internal services
# that don't want to deal w/ cached values. - since with topics now, the library is guaranteed
# not to change until we have a new version, the cached version is good enough
@route("/api/v1/playlists/library/list/fresh", methods=["GET"]) 
@route("/api/v1/playlists/library/list", methods=["GET"])
@jsonp
@decompress # We compress and decompress around layer_cache so memcache never has any trouble storing the large amount of library data.
@cache_with_key_fxn_and_param(
    "casing",
    lambda: "api_library_list_%s" % models.Setting.topic_tree_version(),
    layer=layer_cache.Layers.Memcache)
@compress
@jsonify
def playlists_library_list():
    topics = models.Topic.get_filled_content_topics(types = ["Video", "Url"])

    topics_list = [t for t in topics if not (
        (t.standalone_title == "California Standards Test: Algebra I" and t.id != "algebra-i") or 
        (t.standalone_title == "California Standards Test: Geometry" and t.id != "geometry-2"))    
        ]

    for topic in topics_list:
        topic.videos = topic.children
        topic.title = topic.standalone_title
        del topic.children

    return topics_list
    
@route("/api/v1/exercises", methods=["GET"])
@jsonp
@jsonify
def get_exercises():
    return models.Exercise.get_all_use_cache()

@route("/api/v1/topicversion/<version_id>/exercises/<exercise_name>", methods=["GET"])
@route("/api/v1/exercises/<exercise_name>", methods=["GET"])
@jsonp
@jsonify
def get_exercise(exercise_name, version_id = None):
    version = models.TopicVersion.get_by_id(version_id) if version_id else None
    exercise = models.Exercise.get_by_name(exercise_name, version)
    if exercise and not hasattr(exercise, "related_videos"):
        exercise_videos = exercise.related_videos_query()
        exercise.related_videos = map(lambda exercise_video: exercise_video.video.readable_id, exercise_videos)
    return exercise

@route("/api/v1/exercises/recent", methods=["GET"])
@jsonp
@jsonify
def exercise_recent_list():
    return models.Exercise.all().order('-creation_date').fetch(20)

@route("/api/v1/exercises/<exercise_name>/followup_exercises", methods=["GET"])
@jsonp
@jsonify
def exercise_info(exercise_name):
    exercise = models.Exercise.get_by_name(exercise_name)
    return exercise.followup_exercises() if exercise else []

@route("/api/v1/exercises/<exercise_name>/videos", methods=["GET"])
@jsonp
@jsonify
def exercise_videos(exercise_name):
    exercise = models.Exercise.get_by_name(exercise_name)
    if exercise:
        exercise_videos = exercise.related_videos_query()
        return map(lambda exercise_video: exercise_video.video, exercise_videos)
    return []

@route("/api/v1/topicversion/<version_id>/exercises/<exercise_name>", methods=["POST", "PUT"])
@route("/api/v1/exercises/<exercise_name>", methods=["PUT","POST"])
@developer_required
@jsonp
@jsonify
def exercise_save(exercise_name = None, version_id = "edit"):
    request.json["name"] = exercise_name
    version = models.TopicVersion.get_by_id(version_id)
    query = models.Exercise.all()
    query.filter('name =', exercise_name)
    exercise = query.get()
    return exercise_save_data(version, request.json, exercise)

def exercise_save_data(version, data, exercise=None, put_change=True):
    if "name" not in data:
        raise Exception("exercise 'name' missing")
    data["live"] = data["live"] == "true" or data["live"] == True 
    data["v_position"] = int(data["v_position"])
    data["h_position"] = int(data["h_position"])
    data["seconds_per_fast_problem"] = (
        float(data["seconds_per_fast_problem"]))

    changeable_props = ["name", "covers", "h_position", "v_position", "live",
                        "summative", "prerequisites", "covers", 
                        "related_videos", "short_display_name"]
    if exercise:
        return models.VersionContentChange.add_content_change(exercise, 
            version, 
            data,
            changeable_props)
    else:
        return models.VersionContentChange.add_new_content(models.Exercise, 
                                                           version,
                                                           data,
                                                           changeable_props,
                                                           put_change)

@route("/api/v1/topicversion/<version_id>/videos/<video_id>", methods=["GET"])
@route("/api/v1/videos/<video_id>", methods=["GET"])
@jsonp
@jsonify
def video(video_id, version_id = None):
    version = models.TopicVersion.get_by_id(version_id) if version_id else None
    video = models.Video.get_for_readable_id(video_id, version)

    if video is None:
        video = models.Video.all().filter("youtube_id =", video_id).get()
    
    return video


@route("/api/v1/videos/recent", methods=["GET"])
@jsonp
@jsonify
def video_recent_list():
    return models.Video.all().order('-date_added').fetch(20)

@route("/api/v1/videos/<video_id>/download_available", methods=["POST"])
@oauth_required(require_anointed_consumer=True)
@jsonp
@jsonify
def video_download_available(video_id):

    video = None
    formats = request.request_string("formats", default="")
    allowed_formats = ["mp4", "png", "m3u8"]

    # If for any crazy reason we happen to have multiple entities for a single youtube id,
    # make sure they all have the same downloadable_formats so we don't keep trying to export them.
    for video in models.Video.all().filter("youtube_id =", video_id):

        modified = False

        for downloadable_format in formats.split(","):
            if downloadable_format in allowed_formats and downloadable_format not in video.downloadable_formats:
                video.downloadable_formats.append(downloadable_format)
                modified = True

        if modified:
            video.put()

    return video

@route("/api/v1/videos/<video_id>/exercises", methods=["GET"])
@jsonp
@jsonify
def video_exercises(video_id):
    video = models.Video.all().filter("youtube_id =", video_id).get()
    if video:
        return video.related_exercises(bust_cache=True)
    return []

@route("/api/v1/commoncore", methods=["GET"])
@jsonp
@jsonify
def get_cc_map():
    lightweight = request.request_bool('lightweight', default=False)
    structured = request.request_bool('structured', default=False)
    return CommonCoreMap.get_all(lightweight, structured)

def fully_populated_playlists():
    playlists = models.Playlist.get_for_all_topics()
    video_key_dict = models.Video.get_dict(models.Video.all(), lambda video: video.key())

    video_playlist_query = models.VideoPlaylist.all()
    video_playlist_query.filter('live_association =', True)
    video_playlist_key_dict = models.VideoPlaylist.get_key_dict(video_playlist_query)

    for playlist in playlists:
        playlist.videos = []
        video_playlists = sorted(video_playlist_key_dict[playlist.key()].values(), key=lambda video_playlist: video_playlist.video_position)
        for video_playlist in video_playlists:
            video = video_key_dict[models.VideoPlaylist.video.get_value_for_datastore(video_playlist)]
            video.position = video_playlist.video_position
            playlist.videos.append(video)

    return playlists

# Fetches data from YouTube if we don't have it already in the datastore
@route("/api/v1/videos/<youtube_id>/youtubeinfo", methods=["GET"])
@developer_required
@jsonp
@jsonify
def get_youtube_info(youtube_id):
    video_data = models.Video.all().filter("youtube_id =", youtube_id).get()
    if video_data:
        setattr(video_data, "existing", True)
        return video_data

    video_data = models.Video(youtube_id = youtube_id)
    return youtube_get_video_data(video_data)

@route("/api/v1/topicversion/<version_id>/videos/", methods=["POST", "PUT"])
@route("/api/v1/topicversion/<version_id>/videos/<video_id>", methods=["POST", "PUT"])
@route("/api/v1/videos/", methods=["POST","PUT"])
@route("/api/v1/videos/<video_id>", methods=["POST","PUT"])
@developer_required
@jsonp
@jsonify
def save_video(video_id="", version_id = "edit"):
    version = models.TopicVersion.get_by_id(version_id)
    video = models.Video.get_for_readable_id(video_id, version)

    def check_duplicate(new_data, video=None):
        # make sure we are not changing the video's readable_id to another one's
        query = models.Video.all()
        query = query.filter("readable_id =", new_data["readable_id"])
        if video:
            query = query.filter("__key__ !=", video.key())
        other_video = query.get()
                
        if other_video:
            return api_invalid_param_response(
                "Video with readable_id %s already exists" %
                (new_data["readable_id"]))        
        
        # make sure we are not changing the video's youtube_id to another one's
        query = models.Video.all()
        query = query.filter("youtube_id =", new_data["youtube_id"])
        if video:
            query = query.filter("__key__ !=", video.key())
        other_video = query.get()
        
        if other_video:
            return api_invalid_param_response(
                "Video with youtube_id %s already appears with readable_id %s" %
                (new_data["youtube_id"], video.readable_id)) 

        # make sure we are not changing the video's readable_id to an updated one in the Version's Content Changes
        changes = models.VersionContentChange.get_updated_content_dict(version)
        for key, content in changes.iteritems():
            if type(content) == models.Video and (video is None or 
                                                  key != video.key()): 

                if content.readable_id == new_data["readable_id"]:
                    return api_invalid_param_response(
                        "Video with readable_id %s already exists" %
                        (new_data["readable_id"]))
                       
                elif content.youtube_id == new_data["youtube_id"]:
                    return api_invalid_param_response(
                        "Video with youtube_id %s already appears with readable_id %s" %
                        (new_data["youtube_id"], content.readable_id))  

    if video:
        error = check_duplicate(request.json, video)
        if error:
            return error
        return models.VersionContentChange.add_content_change(video, 
            version, 
            request.json, 
            ["readable_id", "title", "youtube_id", "description", "keywords"])

    # handle making a new video
    else:
        # make sure video doesn't already exist
        error = check_duplicate(request.json)
        if error:
            return error

        video_data = youtube_get_video_data_dict(request.json["youtube_id"])
        if video_data is None:
            return None
        return models.VersionContentChange.add_new_content(models.Video, 
                                                           version,
                                                           video_data)
    
def replace_playlist_values(structure, playlist_dict):
    if type(structure) == list:
        for sub_structure in structure:
            replace_playlist_values(sub_structure, playlist_dict)
    else:
        if "items" in structure:
            replace_playlist_values(structure["items"], playlist_dict)
        elif "playlist" in structure:
            # Replace string playlist title with real playlist object
            key = structure["playlist"]
            if key in playlist_dict:
                structure["playlist"] = playlist_dict[key]
            else:
                del structure["playlist"]

def get_students_data_from_request(user_data):
    return util_profile.get_students_data(user_data, request.request_string("list_id"))

@route("/api/v1/user", methods=["GET"])
@oauth_required()
@jsonp
@jsonify
def user_data_other():
    user_data = models.UserData.current()

    if user_data:
        user_data_student = get_visible_user_data_from_request()
        if user_data_student:
            return user_data_student

    return None

@route("/api/v1/user/username_available", methods=["GET"])
@jsonp
@jsonify
def is_username_available():
    """ Return whether username is available.
    """
    username = request.request_string('username')
    if not username:
        return False
    else:
        return models.UniqueUsername.is_available_username(username)

@route("/api/v1/user/promo/<promo_name>", methods=["GET"])
@oauth_required()
@jsonp
@jsonify
def has_seen_promo(promo_name):
    user_data = models.UserData.current()
    return models.PromoRecord.has_user_seen_promo(promo_name, user_data.user_id)

@route("/api/v1/user/promo/<promo_name>", methods=["POST"])
@oauth_required()
@jsonp
@jsonify
def mark_promo_as_seen(promo_name):
    user_data = models.UserData.current()
    return models.PromoRecord.record_promo(promo_name, user_data.user_id)

# TODO: the "GET" version of this.
@route("/api/v1/user/profile", methods=["POST", "PUT"])
@oauth_required()
@jsonp
@jsonify
def update_user_profile():
    """ Update public information about a user.
    
    The posted data should be JSON, with fields representing the values that
    needs to be changed. Supports "user_nickname", "avatar_name",
    "username", and "isPublic".
    """
    user_data = models.UserData.current()

    profile_json = request.json
    if not profile_json:
        return api_invalid_param_response("Profile data expected")
    
    if profile_json['nickname'] is not None:
        user_data.update_nickname(profile_json['nickname'])

    badge_awarded = False
    if profile_json['avatarName'] is not None:
        avatar_name = profile_json['avatarName']
        name_dict = util_avatars.avatars_by_name()

        # Ensure that the avatar is actually valid and that the user can
        # indeed earn it.
        if (avatar_name in name_dict
                and user_data.avatar_name != avatar_name
                and name_dict[avatar_name].is_satisfied_by(user_data)):
            user_data.avatar_name = avatar_name
            if profile_badges.ProfileCustomizationBadge.mark_avatar_changed(user_data):
                profile_badges.ProfileCustomizationBadge().award_to(user_data)
                badge_awarded = True

    if profile_json['isPublic'] is not None:
        user_data.is_profile_public = profile_json['isPublic']

    if profile_json['username']:
        username = profile_json['username']
        if ((username != user_data.username) and
                not user_data.claim_username(username)):
            # TODO: How much do we want to communicate to the user?
            return api_invalid_param_response("Error!")

    user_data.put()

    result = util_profile.UserProfile.from_user(user_data, user_data)
    if badge_awarded:
        result = {
            'payload': result,
            'action_results': None,
        }
        add_action_results(result, {})
    return result

@route("/api/v1/user/coaches", methods=["PUT"])
@oauth_required()
@jsonp
@jsonify
def add_coach():
    """ Add a coach for the currently logged in user.

    Expects JSON with a "username" or "email" field that specifies the coach.
    """
    # TODO: Remove redundant path/logic in coaches.py
    coach_user_data = get_user_data_from_json(request.json, 'coach')

    if not coach_user_data:
        return api_invalid_param_response("Invalid coach email or username.")

    current_user_data = models.UserData.current()
    if not current_user_data.is_coached_by(coach_user_data):
        current_user_data.coaches.append(coach_user_data.key_email)
        current_user_data.put()

@route("/api/v1/user/coaches", methods=["DELETE"])
@oauth_required()
@jsonp
@jsonify
def remove_coach():
    """ Remove a coach for the currently logged in user.

    Expects JSON with a "username" or "email" field that specifies the coach.
    """
    # TODO: Remove redundant path/logic in coaches.py
    coach_user_data = get_user_data_from_json(request.json, 'coach')

    if not coach_user_data:
        return api_invalid_param_response("Invalid coach email or username.")

    current_user_data = models.UserData.current()

    if current_user_data.student_lists:
        actual_lists = StudentList.get(current_user_data.student_lists)
        current_user_data.student_lists = [l.key() for l in actual_lists if coach_user_data.key() not in l.coaches]

    try:
        current_user_data.coaches.remove(coach_user_data.key_email)
    except ValueError:
        pass

    try:
        current_user_data.coaches.remove(coach_user_data.key_email.lower())
    except ValueError:
        pass

    current_user_data.put()

@route("/api/v1/user/students", methods=["GET"])
@oauth_required()
@jsonp
@jsonify
def user_data_student():
    user_data = models.UserData.current()

    if user_data:
        user_data_student = get_visible_user_data_from_request(disable_coach_visibility=True)
        if user_data_student:
            return get_students_data_from_request(user_data_student)

    return None

@route("/api/v1/user/studentlists", methods=["GET"])
@oauth_required()
@jsonp
@jsonify
def get_user_studentlists():
    user_data = models.UserData.current()

    if user_data:
        user_data_student = get_visible_user_data_from_request()
        if user_data_student:
            student_lists_model = StudentList.get_for_coach(user_data_student.key())
            student_lists = []
            for student_list in student_lists_model:
                student_lists.append({
                    'key': str(student_list.key()),
                    'name': student_list.name,
                })
            return student_lists

    return None

@route("/api/v1/user/studentlists", methods=["POST"])
@oauth_optional()
@jsonp
@jsonify
def create_user_studentlist():
    coach_data = models.UserData.current()
    if not coach_data:
        return unauthorized_response()

    list_name = request.request_string('list_name').strip()
    if not list_name:
        raise Exception('Invalid list name')

    student_list = models.StudentList(coaches=[coach_data.key()],
        name=list_name)
    student_list.put()

    student_list_json = {
        'name': student_list.name,
        'key': str(student_list.key())
    }
    return student_list_json

@route("/api/v1/user/studentlists/<list_key>", methods=["DELETE"])
@oauth_optional()
@jsonp
@jsonify
def delete_user_studentlist(list_key):
    coach_data = models.UserData.current()
    if not coach_data:
        return unauthorized_response()

    student_list = util_profile.get_student_list(coach_data, list_key)
    student_list.delete()
    return True

def filter_query_by_request_dates(query, property):

    if request.request_string("dt_start"):
        try:
            dt_start = request.request_date_iso("dt_start")
            query.filter("%s >=" % property, dt_start)
        except ValueError:
            raise ValueError("Invalid date format sent to dt_start, use ISO 8601 Combined.")

    if request.request_string("dt_end"):
        try:
            dt_end = request.request_date_iso("dt_end")
            query.filter("%s <" % property, dt_end)
        except ValueError:
            raise ValueError("Invalid date format sent to dt_end, use ISO 8601 Combined.")

@route("/api/v1/user/videos", methods=["GET"])
@oauth_required()
@jsonp
@jsonify
def user_videos_all():
    user_data = models.UserData.current()

    if user_data:
        user_data_student = get_visible_user_data_from_request()

        if user_data_student:
            user_videos_query = models.UserVideo.all().filter("user =", user_data_student.user)

            try:
                filter_query_by_request_dates(user_videos_query, "last_watched")
            except ValueError, e:
                return api_error_response(e)

            return user_videos_query.fetch(10000)

    return None

@route("/api/v1/user/videos/<youtube_id>", methods=["GET"])
@oauth_optional()
@jsonp
@jsonify
def user_videos_specific(youtube_id):
    user_data = models.UserData.current()

    if user_data and youtube_id:
        user_data_student = get_visible_user_data_from_request()
        video = models.Video.all().filter("youtube_id =", youtube_id).get()

        if user_data_student and video:
            user_videos = models.UserVideo.all().filter("user =", user_data_student.user).filter("video =", video)
            return user_videos.get()

    return None

# Can specify video using "video_key" parameter instead of youtube_id.
# Supports a GET request to solve the IE-behind-firewall issue with occasionally stripped POST data.
# See http://code.google.com/p/khanacademy/issues/detail?id=3098
# and http://stackoverflow.com/questions/328281/why-content-length-0-in-post-requests
@route("/api/v1/user/videos/<youtube_id>/log", methods=["POST"])
@route("/api/v1/user/videos/<youtube_id>/log_compatability", methods=["GET"])
@oauth_optional(require_anointed_consumer=True)
@api_create_phantom
@jsonp
@jsonify
def log_user_video(youtube_id):
    if (not request.request_string("seconds_watched") or
        not request.request_string("last_second_watched")):
        logging.critical("Video log request with no parameters received.")
        return api_invalid_param_response("Must supply seconds_watched and" +
            "last_second_watched")

    user_data = models.UserData.current()
    if not user_data:
        logging.warning("Video watched with no user_data present")
        return unauthorized_response()

    video_key_str = request.request_string("video_key")

    if not youtube_id and not video_key_str:
        return api_invalid_param_response("Must supply youtube_id or video_key")

    if video_key_str:
        key = db.Key(video_key_str)
        video = db.get(key)
    else:
        video = models.Video.all().filter("youtube_id =", youtube_id).get()

    if not video:
        logging.error("Could not find video for %s" % (video_key_str or youtube_id))
        return api_invalid_param_response("Could not find video for %s" % (video_key_str or youtube_id))

    seconds_watched = int(request.request_float("seconds_watched", default=0))
    last_second = int(request.request_float("last_second_watched", default=0))

    user_video, video_log, _, goals_updated = models.VideoLog.add_entry(
        user_data, video, seconds_watched, last_second)

    if video_log:
        action_results = {}
        action_results['user_video'] = user_video
        if goals_updated:
            action_results['updateGoals'] = [g.get_visible_data(None)
                for g in goals_updated]

        add_action_results(video_log, action_results)

    return video_log


@route("/api/v1/user/exercises", methods=["GET"])
@oauth_optional()
@jsonp
@jsonify
def user_exercises_all():
    """ Retrieves the list of exercise models wrapped inside of an object that
    gives information about what sorts of progress and interaction the current
    user has had with it.

    Defaults to a pre-phantom users, in which case the encasing object is
    skeletal and contains little information.

    """
    user_data = models.UserData.current()

    if not user_data:
        user_data = models.UserData.pre_phantom()
    student = get_visible_user_data_from_request(user_data=user_data)
    exercises = models.Exercise.get_all_use_cache()
    user_exercise_graph = models.UserExerciseGraph.get(student)
    if student.is_pre_phantom:
        user_exercises = []
    else:
        user_exercises = (models.UserExercise.all().
                          filter("user =", student.user).
                          fetch(10000))

    user_exercises_dict = dict((user_exercise.exercise, user_exercise)
                               for user_exercise in user_exercises)

    results = []
    for exercise in exercises:
        name = exercise.name
        if name not in user_exercises_dict:
            user_exercise = models.UserExercise()
            user_exercise.exercise = name
            user_exercise.user = student.user
        else:
            user_exercise = user_exercises_dict[name]
        user_exercise.exercise_model = exercise
        user_exercise._user_data = student
        user_exercise._user_exercise_graph = user_exercise_graph
        results.append(user_exercise)

    return results

@route("/api/v1/user/students/progress/summary", methods=["GET"])
@oauth_required()
@jsonp
@jsonify
def get_students_progress_summary():
    user_data_coach = get_user_data_coach_from_request()

    try:
        list_students = get_students_data_from_request(user_data_coach)
    except Exception, e:
        return api_invalid_param_response(e.message)

    list_students = sorted(list_students, key=lambda student: student.nickname)
    user_exercise_graphs = models.UserExerciseGraph.get(list_students)

    student_review_exercise_names = []
    for user_exercise_graph in user_exercise_graphs:
        student_review_exercise_names.append(user_exercise_graph.review_exercise_names())

    exercises = models.Exercise.get_all_use_cache()
    exercise_data = []

    for exercise in exercises:
        progress_buckets = {
            'review': [],
            'proficient': [],
            'struggling': [],
            'started': [],
            'not-started': [],
        }

        for (student, user_exercise_graph, review_exercise_names) in izip(
                list_students, user_exercise_graphs,
                student_review_exercise_names):
            graph_dict = user_exercise_graph.graph_dict(exercise.name)

            if graph_dict['proficient']:
                if exercise.name in review_exercise_names:
                    status = 'review'
                else:
                    status = 'proficient'
            elif graph_dict['struggling']:
                status = 'struggling'
            elif graph_dict['total_done'] > 0:
                status = 'started'
            else:
                status = 'not-started'

            progress_buckets[status].append({
                    'nickname': student.nickname,
                    'email': student.email,
                    'profile_root': student.profile_root,
            })

        progress = [dict([('status', status),
                        ('students', progress_buckets[status])])
                        for status in progress_buckets]

        exercise_data.append({
            'name': exercise.name,
            'display_name': exercise.display_name,
            'progress': progress,
        })

    return {'exercises': exercise_data,
            'num_students': len(list_students)}

@route("/api/v1/user/exercises/<exercise_name>", methods=["GET"])
@oauth_optional()
@jsonp
@jsonify
def user_exercises_specific(exercise_name):
    user_data = models.UserData.current()

    if user_data and exercise_name:
        user_data_student = get_visible_user_data_from_request()
        exercise = models.Exercise.get_by_name(exercise_name)

        if user_data_student and exercise:
            user_exercise = models.UserExercise.all().filter("user =", user_data_student.user).filter("exercise =", exercise_name).get()

            if not user_exercise:
                user_exercise = models.UserExercise()
                user_exercise.exercise_model = exercise
                user_exercise.exercise = exercise_name
                user_exercise.user = user_data_student.user

            # Cheat and send back related videos when grabbing a single UserExercise for ease of exercise integration
            user_exercise.exercise_model.related_videos = map(lambda exercise_video: exercise_video.video, user_exercise.exercise_model.related_videos_fetch())
            return user_exercise

    return None

def user_followup_exercises(exercise_name):
    user_data = models.UserData.current()

    if user_data and exercise_name:

        user_data_student = get_visible_user_data_from_request()
        user_exercise_graph = models.UserExerciseGraph.get(user_data)

        user_exercises = models.UserExercise.all().filter("user =", user_data_student.user).fetch(10000)
        followup_exercises = models.Exercise.get_by_name(exercise_name).followup_exercises()

        followup_exercises_dict = dict((exercise.name, exercise) for exercise in followup_exercises)
        user_exercises_dict = dict((user_exercise.exercise, user_exercise) for user_exercise in user_exercises
                                                                            if user_exercise in followup_exercises)

        # create user_exercises that haven't been attempted yet
        for exercise_name in followup_exercises_dict:
            if not exercise_name in user_exercises_dict:
                user_exercise = models.UserExercise()
                user_exercise.exercise = exercise_name
                user_exercise.user = user_data_student.user
                user_exercises_dict[exercise_name] = user_exercise

        for exercise_name in user_exercises_dict:
            if exercise_name in followup_exercises_dict:
                user_exercises_dict[exercise_name].exercise_model = followup_exercises_dict[exercise_name]
                user_exercises_dict[exercise_name]._user_data = user_data_student
                user_exercises_dict[exercise_name]._user_exercise_graph = user_exercise_graph

        return user_exercises_dict.values()

    return None

@route("/api/v1/user/exercises/<exercise_name>/followup_exercises", methods=["GET"])
@oauth_optional()
@jsonp
@jsonify
def api_user_followups(exercise_name):
    return user_followup_exercises(exercise_name)

@route("/api/v1/user/topics", methods=["GET"])
@route("/api/v1/user/playlists", methods=["GET"])
@oauth_required()
@jsonp
@jsonify
def user_playlists_all():
    user_data = models.UserData.current()

    if user_data:
        user_data_student = get_visible_user_data_from_request()

        if user_data_student:
            user_playlists = models.UserTopic.all().filter("user =", user_data_student.user)
            return user_playlists.fetch(10000)

    return None

@route("/api/v1/user/topic/<topic_id>", methods=["GET"])
@route("/api/v1/user/playlists/<topic_id>", methods=["GET"])
@oauth_required()
@jsonp
@jsonify
def user_playlists_specific(topic_id):
    user_data = models.UserData.current()

    if user_data and playlist_title:
        user_data_student = get_visible_user_data_from_request()
        topic = models.Topic.get_by_id(topic_id)
        if topic is None:
            topic = models.Topic.all().filter("standalone_title =", topic_id).get()

        if user_data_student and topic:
            return models.UserTopic.get_for_topic_and_user_data(topic, user_data_student)

    return None

@route("/api/v1/user/exercises/<exercise_name>/log", methods=["GET"])
@oauth_required()
@jsonp
@jsonify
def user_problem_logs(exercise_name):
    user_data = models.UserData.current()

    if user_data and exercise_name:
        user_data_student = get_visible_user_data_from_request()
        exercise = models.Exercise.get_by_name(exercise_name)

        if user_data_student and exercise:

            problem_log_query = models.ProblemLog.all()
            problem_log_query.filter("user =", user_data_student.user)
            problem_log_query.filter("exercise =", exercise.name)

            try:
                filter_query_by_request_dates(problem_log_query, "time_done")
            except ValueError, e:
                return api_error_response(e)

            problem_log_query.order("time_done")

            return problem_log_query.fetch(500)

    return None

# TODO(david): Factor out duplicated code between attempt_problem_number and
#     hint_problem_number.
@route("/api/v1/user/exercises/<exercise_name>/problems/<int:problem_number>/attempt", methods=["POST"])
@oauth_optional()
@api_create_phantom
@jsonp
@jsonify
def attempt_problem_number(exercise_name, problem_number):
    user_data = models.UserData.current()

    if user_data:
        exercise = models.Exercise.get_by_name(exercise_name)
        user_exercise = user_data.get_or_insert_exercise(exercise)

        if user_exercise and problem_number:

            review_mode = request.request_bool("review_mode", default=False)

            user_exercise, user_exercise_graph, goals_updated = attempt_problem(
                    user_data,
                    user_exercise,
                    problem_number,
                    request.request_int("attempt_number"),
                    request.request_string("attempt_content"),
                    request.request_string("sha1"),
                    request.request_string("seed"),
                    request.request_bool("complete"),
                    request.request_int("count_hints", default=0),
                    int(request.request_float("time_taken")),
                    review_mode,
                    request.request_string("non_summative"),
                    request.request_string("problem_type"),
                    request.remote_addr,
                    )

            # this always returns a delta of points earned each attempt
            points_earned = user_data.points - user_data.original_points()
            if(user_exercise.streak == 0):
                # never award points for a zero streak
                points_earned = 0
            if(user_exercise.streak == 1):
                # award points for the first correct exercise done, even if no prior history exists
                # and the above pts-original points gives a wrong answer
                points_earned = user_data.points if (user_data.points == points_earned) else points_earned

            user_states = user_exercise_graph.states(exercise.name)
            correct = request.request_bool("complete")

            action_results = {
                "exercise_state": {
                    "state": [state for state in user_states if user_states[state]],
                    "template" : templatetags.exercise_message(exercise,
                        user_exercise_graph, review_mode=review_mode),
                },
                "points_earned": {"points": points_earned},
                "attempt_correct": correct,
            }

            if goals_updated:
                action_results['updateGoals'] = [g.get_visible_data(None) for g in goals_updated]

            if review_mode:
                action_results['reviews_left'] = (
                    user_exercise_graph.reviews_left_count() + (1 - correct))

            add_action_results(user_exercise, action_results)
            return user_exercise

    logging.warning("Problem %d attempted with no user_data present", problem_number)
    return unauthorized_response()

@route("/api/v1/user/exercises/<exercise_name>/problems/<int:problem_number>/hint", methods=["POST"])
@oauth_optional()
@api_create_phantom
@jsonp
@jsonify
def hint_problem_number(exercise_name, problem_number):

    user_data = models.UserData.current()

    if user_data:
        exercise = models.Exercise.get_by_name(exercise_name)
        user_exercise = user_data.get_or_insert_exercise(exercise)

        if user_exercise and problem_number:

            prev_user_exercise_graph = models.UserExerciseGraph.get(user_data)

            attempt_number = request.request_int("attempt_number")
            count_hints = request.request_int("count_hints")
            review_mode = request.request_bool("review_mode", default=False)

            user_exercise, user_exercise_graph, goals_updated = attempt_problem(
                    user_data,
                    user_exercise,
                    problem_number,
                    attempt_number,
                    request.request_string("attempt_content"),
                    request.request_string("sha1"),
                    request.request_string("seed"),
                    request.request_bool("complete"),
                    count_hints,
                    int(request.request_float("time_taken")),
                    review_mode,
                    request.request_string("non_summative"),
                    request.request_string("problem_type"),
                    request.remote_addr,
                    )

            user_states = user_exercise_graph.states(exercise.name)
            exercise_message_html = templatetags.exercise_message(exercise,
                    user_exercise_graph, review_mode=review_mode)

            add_action_results(user_exercise, {
                "exercise_message_html": exercise_message_html,
                "exercise_state": {
                    "state": [state for state in user_states if user_states[state]],
                    "template" : exercise_message_html,
                }
            })

            # A hint will count against the user iff they haven't attempted the question yet and it's their first hint
            if attempt_number == 0 and count_hints == 1:
                bingo("hints_costly_hint")
                bingo("hints_costly_hint_binary")

            return user_exercise

    logging.warning("Problem %d attempted with no user_data present", problem_number)
    return unauthorized_response()

# TODO: Remove this route in v2
@route("/api/v1/user/exercises/<exercise_name>/reset_streak", methods=["POST"])
@oauth_optional()
@jsonp
@jsonify
def reset_problem_streak(exercise_name):
    return _attempt_problem_wrong(exercise_name)

@route("/api/v1/user/exercises/<exercise_name>/wrong_attempt", methods=["POST"])
@oauth_optional()
@jsonp
@jsonify
def attempt_problem_wrong(exercise_name):
    return _attempt_problem_wrong(exercise_name)

def _attempt_problem_wrong(exercise_name):
    user_data = models.UserData.current()

    if user_data and exercise_name:
        user_exercise = user_data.get_or_insert_exercise(models.Exercise.get_by_name(exercise_name))
        return make_wrong_attempt(user_data, user_exercise)

    return unauthorized_response()

@route("/api/v1/user/exercises/review_problems", methods=["GET"])
@oauth_optional()
@jsonp
@jsonify
def get_ordered_review_problems():
    """Retrieves an ordered list of a subset of the upcoming review problems."""

    # TODO(david): This should probably be abstracted away in exercises.py or
    # models.py (if/when there's more logic here) with a nice interface.

    user_data = get_visible_user_data_from_request()

    if not user_data:
        return []

    user_exercise_graph = models.UserExerciseGraph.get(user_data)
    review_exercises = user_exercise_graph.review_exercise_names()

    queued_exercises = request.request_string('queued', '').split(',')

    # Only return those exercises that aren't already queued up
    return filter(lambda ex: ex not in queued_exercises, review_exercises)

@route("/api/v1/user/videos/<youtube_id>/log", methods=["GET"])
@oauth_required()
@jsonp
@jsonify
def user_video_logs(youtube_id):
    user_data = models.UserData.current()

    if user_data and youtube_id:
        user_data_student = get_visible_user_data_from_request()
        video = models.Video.all().filter("youtube_id =", youtube_id).get()

        if user_data_student and video:

            video_log_query = models.VideoLog.all()
            video_log_query.filter("user =", user_data_student.user)
            video_log_query.filter("video =", video)

            try:
                filter_query_by_request_dates(video_log_query, "time_watched")
            except ValueError, e:
                return api_error_response(e)

            video_log_query.order("time_watched")

            return video_log_query.fetch(500)

    return None

# TODO: this should probably not return user data in it.
@route("/api/v1/badges", methods=["GET"])
@oauth_optional()
@jsonp
@jsonify
def badges_list():
    badges_dict = util_badges.all_badges_dict()

    user_data = models.UserData.current()
    if user_data:

        user_data_student = get_visible_user_data_from_request()
        if user_data_student:

            user_badges = models_badges.UserBadge.get_for(user_data_student)

            for user_badge in user_badges:

                badge = badges_dict.get(user_badge.badge_name)

                if badge:
                    if not hasattr(badge, "user_badges"):
                        badge.user_badges = []
                    badge.user_badges.append(user_badge)
                    badge.is_owned = True

    return sorted(filter(lambda badge: not badge.is_hidden(), badges_dict.values()), key=lambda badge: badge.name)

@route("/api/v1/badges/categories", methods=["GET"])
@jsonp
@jsonify
def badge_categories():
    return badges.BadgeCategory.all()

@route("/api/v1/badges/categories/<category>", methods=["GET"])
@jsonp
@jsonify
def badge_category(category):
    return filter(lambda badge_category: str(badge_category.category) == category, badges.BadgeCategory.all())

# TODO: the "GET" version of this.
@route("/api/v1/user/badges/public", methods=["POST", "PUT"])
@oauth_required()
@jsonp
@jsonify
def update_public_user_badges():
    user_data = models.UserData.current()
    if not user_data:
        return api_invalid_param_response("User not logged in")

    owned_badges = set([badges.Badge.remove_target_context(name_with_context)
                        for name_with_context in user_data.badges])
    badges_dict = util_badges.all_badges_dict()
    updated_badge_list = []
    empty_name = util_badges.EMPTY_BADGE_NAME
    for name in request.json or []:
        if name in owned_badges:
            updated_badge_list.append(badges_dict[name])
        elif name == empty_name:
            updated_badge_list.append(None)
    
    badge_awarded = False
    if (len(updated_badge_list) == util_badges.NUM_PUBLIC_BADGE_SLOTS
            and not any([badge is None for badge in updated_badge_list])):
        if profile_badges.ProfileCustomizationBadge.mark_display_case_filled(user_data):
            profile_badges.ProfileCustomizationBadge().award_to(user_data)
            badge_awarded = True

    user_data.public_badges = [(badge.name if badge else empty_name)
                               for badge in updated_badge_list]
    user_data.put()
    
    result = updated_badge_list
    if badge_awarded:
        result = {
            'payload': result,
            'api_action_results': None
        }
        add_action_results(result, {})
    return result

@route("/api/v1/user/badges", methods=["GET"])
@oauth_optional()
@jsonp
@jsonify
def get_user_badges():
    user_data = get_visible_user_data_from_request() or models.UserData.pre_phantom()
    grouped_badges = util_badges.get_grouped_user_badges(user_data)

    user_badges_by_category = {
        badges.BadgeCategory.BRONZE: grouped_badges["bronze_badges"],
        badges.BadgeCategory.SILVER: grouped_badges["silver_badges"],
        badges.BadgeCategory.GOLD: grouped_badges["gold_badges"],
        badges.BadgeCategory.PLATINUM: grouped_badges["platinum_badges"],
        badges.BadgeCategory.DIAMOND: grouped_badges["diamond_badges"],
        badges.BadgeCategory.MASTER: grouped_badges["user_badges_master"],
    }

    user_badge_dicts_by_category = {}

    for category, user_badge_bucket in user_badges_by_category.iteritems():
        user_badge_dicts_by_category[category] = user_badge_bucket

    badge_collections = []

    # Iterate over the set of all possible badges.
    for collection in grouped_badges["badge_collections"]:
        if len(collection):
            first_badge = collection[0]
            badge_collections.append({
                "category": first_badge.badge_category,
                "category_description": first_badge.category_description(),
                "badges": collection,
                "user_badges": user_badge_dicts_by_category[first_badge.badge_category],
            })

    return {
            "badge_collections": badge_collections,
        }

@route("/api/v1/user/activity", methods=["GET"])
@oauth_required()
@jsonp
@jsonify
def get_activity():
    student = models.UserData.current() or models.UserData.pre_phantom()
    user_override = request.request_user_data("email")
    if user_override and user_override.key_email != student.key_email:
        # TODO: Clarify "visibility"
        if not user_override.is_visible_to(student):
            return api_unauthorized_response("Cannot view this profile")
        else:
            # Allow access to this student's profile
            student = user_override

    recent_activities = recent_activity.recent_activity_list(student)
    recent_completions = filter(
            lambda activity: activity.is_complete(),
            recent_activities)

    return {
        "suggested": suggested_activity.SuggestedActivity.get_for(
                student, recent_activities),
        "recent": recent_completions[:recent_activity.MOST_RECENT_ITEMS],
    }

# TODO in v2: imbue with restfulness
@route("/api/v1/developers/add", methods=["POST"])
@admin_required
@jsonp
@jsonify
def add_developer():
    user_data_developer = request.request_user_data("email")

    if not user_data_developer:
        return False

    user_data_developer.developer = True
    user_data_developer.put()

    return True

@route("/api/v1/developers/remove", methods=["POST"])
@admin_required
@jsonp
@jsonify
def remove_developer():
    user_data_developer = request.request_user_data("email")

    if not user_data_developer:
        return False

    user_data_developer.developer = False
    user_data_developer.put()

    return True

@route("/api/v1/coworkers/add", methods=["POST"])
@developer_required
@jsonp
@jsonify
def add_coworker():
    user_data_coach = request.request_user_data("coach_email")
    user_data_coworker = request.request_user_data("coworker_email")

    if user_data_coach and user_data_coworker:
        if not user_data_coworker.key_email in user_data_coach.coworkers:
            user_data_coach.coworkers.append(user_data_coworker.key_email)
            user_data_coach.put()

        if not user_data_coach.key_email in user_data_coworker.coworkers:
            user_data_coworker.coworkers.append(user_data_coach.key_email)
            user_data_coworker.put()

    return True

@route("/api/v1/coworkers/remove", methods=["POST"])
@developer_required
@jsonp
@jsonify
def remove_coworker():
    user_data_coach = request.request_user_data("coach_email")
    user_data_coworker = request.request_user_data("coworker_email")

    if user_data_coach and user_data_coworker:
        if user_data_coworker.key_email in user_data_coach.coworkers:
            user_data_coach.coworkers.remove(user_data_coworker.key_email)
            user_data_coach.put()

        if user_data_coach.key_email in user_data_coworker.coworkers:
            user_data_coworker.coworkers.remove(user_data_coach.key_email)
            user_data_coworker.put()

    return True

@route("/api/v1/autocomplete", methods=["GET"])
@jsonp
@jsonify
def autocomplete():

    video_results = []

    query = request.request_string("q", default="").strip().lower()
    if query:

        max_results_per_type = 10

        exercise_results = filter(
                lambda exercise: query in exercise.display_name.lower(),
                models.Exercise.get_all_use_cache())
        video_results = filter(
                lambda video_dict: query in video_dict["title"].lower(),
                video_title_dicts())
        topic_results = filter(
                lambda topic_dict: query in topic_dict["title"].lower(),
                topic_title_dicts())
        topic_results.extend(map(lambda topic: {
                "title": topic.standalone_title,
                "key": str(topic.key()),
                "relative_url": topic.relative_url,
                "id": topic.id
            }, filter(lambda topic: query in topic.title.lower(), models.Topic.get_super_topics())))
        url_results = filter(
                lambda url_dict: query in url_dict["title"].lower(),
                url_title_dicts())

        exercise_results = sorted(
                exercise_results,
                key=lambda v: v.display_name.lower().index(query))[:max_results_per_type]
        video_results = sorted(
                video_results + url_results,
                key=lambda v: v["title"].lower().index(query))[:max_results_per_type]
        topic_results = sorted(
                topic_results,
                key=lambda t: t["title"].lower().index(query))[:max_results_per_type]

    return {
            "query": query,
            "videos": video_results,
            "topics": topic_results,
            "exercises": exercise_results
    }

@route("/api/v1/dev/backupmodels", methods=["GET"])
@oauth_required()
@developer_required
@jsonify
def backupmodels():
    """Return the names of all models that inherit from models.BackupModel."""
    return map(lambda x: x.__name__, models.BackupModel.__subclasses__())

@route("/api/v1/dev/protobufquery", methods=["GET"])
@oauth_required()
@developer_required
@pickle
def protobuf_query():
    """Return the results of a GQL query as pickled protocol buffer objects

    Example python code:
    import urllib as u
    import urllib2 as u2

    # make sure to quote the query
    q = u.quote("SELECT * FROM VideoLog ORDER BY time_watched LIMIT 50")

    # get the entities selected by the query
    p = u2.urlopen("http://localhost:8080/api/v1/dev/protobufquery?query=%s" % q)

    # It's a little more complicated in practice because oauth must be used but
    # that's the idea
    """

    query = request.request_string("query")
    if not query:
        return api_error_response(ValueError("Query required"))

    return map(lambda entity: db.model_to_protobuf(entity).Encode(),
               db.GqlQuery(query))

@route("/api/v1/dev/protobuf/<entity>", methods=["GET"])
@oauth_required()
@developer_required
@pickle
def protobuf_entities(entity):
    """Return up to 'max' entities last altered between 'dt_start' and 'dt_end'.

    Notes: 'entity' must be a subclass of 'models.BackupModel'
           'dt{start,end}' must be in ISO 8601 format
           'max' defaults to 500
    Example:
        /api/v1/dev/protobuf/ProblemLog?dt_start=2012-02-11T20%3A07%3A49Z&dt_end=2012-02-11T21%3A07%3A49Z
        Returns up to 500 problem_logs from between 'dt_start' and 'dt_end'
    """
    entity_class = db.class_for_kind(entity)
    if not (entity_class and issubclass(entity_class, models.BackupModel)):
        return api_error_response(ValueError("Invalid class '%s' (must be a \
                subclass of models.BackupModel)" % entity))
    query = entity_class.all()
    filter_query_by_request_dates(query, "backup_timestamp")
    query.order("backup_timestamp")

    return map(lambda entity: db.model_to_protobuf(entity).Encode(),
               query.fetch(request.request_int("max", default=500)))

@route("/api/v1/dev/problems", methods=["GET"])
@oauth_required()
@developer_required
@jsonp
@jsonify
def problem_logs():
    problem_log_query = models.ProblemLog.all()
    filter_query_by_request_dates(problem_log_query, "time_done")
    problem_log_query.order("time_done")
    return problem_log_query.fetch(request.request_int("max", default=500))

@route("/api/v1/dev/videos", methods=["GET"])
@oauth_required()
@developer_required
@jsonp
@jsonify
def video_logs():
    video_log_query = models.VideoLog.all()
    filter_query_by_request_dates(video_log_query, "time_watched")
    video_log_query.order("time_watched")
    return video_log_query.fetch(request.request_int("max", default=500))

@route("/api/v1/dev/users", methods=["GET"])
@oauth_required()
@developer_required
@jsonp
@jsonify
def user_data():
    user_data_query = models.UserData.all()
    filter_query_by_request_dates(user_data_query, "joined")
    user_data_query.order("joined")
    return user_data_query.fetch(request.request_int("max", default=500))

@route("/api/v1/user/students/progressreport", methods=["GET"])
@oauth_optional()
@jsonp
@jsonify
def get_student_progress_report():
    user_data_coach = get_user_data_coach_from_request()

    if not user_data_coach:
        return api_invalid_param_response("User is not logged in.")

    try:
        students = get_students_data_from_request(user_data_coach)
    except Exception, e:
        return api_invalid_param_response(e.message)

    return class_progress_report_graph.class_progress_report_graph_context(
        user_data_coach, students)

@route("/api/v1/user/goals", methods=["GET"])
@oauth_optional()
@jsonp
@jsonify
def get_user_goals():
    student = models.UserData.current() or models.UserData.pre_phantom()
    user_override = request.request_user_data("email")
    if user_override and user_override.key_email != student.key_email:
        if not user_override.is_visible_to(student):
            return api_unauthorized_response("Cannot view this profile")
        else:
            # Allow access to this student's profile
            student = user_override

    goals = GoalList.get_all_goals(student)
    return [g.get_visible_data() for g in goals]

@route("/api/v1/user/goals/current", methods=["GET"])
@oauth_optional()
@jsonp
@jsonify
def get_user_current_goals():
    student = models.UserData.current() or models.UserData.pre_phantom()

    user_override = request.request_user_data("email")
    if user_override and user_override.key_email != student.key_email:
        if not user_override.is_visible_to(student):
            return api_unauthorized_response("Cannot view this profile")
        else:
            # Allow access to this student's profile
            student = user_override

    goals = GoalList.get_current_goals(student)
    return [g.get_visible_data() for g in goals]

@route("/api/v1/user/students/goals", methods=["GET"])
@oauth_optional()
@jsonp
@jsonify
def get_student_goals():
    user_data_coach = get_user_data_coach_from_request()

    try:
        students = get_students_data_from_request(user_data_coach)
    except Exception, e:
        return api_invalid_param_response(e.message)

    dt_end = datetime.datetime.now()
    days = request.request_int("days", 7)
    dt_start = dt_end - datetime.timedelta(days=days)

    students = sorted(students, key=lambda student: student.nickname)
    user_exercise_graphs = models.UserExerciseGraph.get(students)

    return_data = []
    for student, uex_graph in izip(students, user_exercise_graphs):
        goals = GoalList.get_modified_between_dts(student, dt_start, dt_end)
        goals = [g.get_visible_data(uex_graph) for g in goals if not g.abandoned]

        return_data.append({
            'email': student.email,
            'profile_root': student.profile_root,
            'goals': goals,
            'nickname': student.nickname,
        })

    return return_data

@route("/api/v1/user/goals", methods=["POST"])
@oauth_optional()
@api_create_phantom
@jsonp
@jsonify
def create_user_goal():
    user_data = models.UserData.current()
    if not user_data:
        return api_invalid_param_response("User is not logged in.")

    user_override = request.request_user_data("email")
    if user_data.developer and user_override and user_override.key_email != user_data.key_email:
        user_data = user_override

    json = request.json
    title = json.get('title')
    if not title:
        return api_invalid_param_response('Title is invalid.')

    objective_descriptors = []

    goal_videos = GoalList.videos_in_current_goals(user_data)
    current_goals = GoalList.get_current_goals(user_data)

    if json:
        for obj in json['objectives']:
            if obj['type'] == 'GoalObjectiveAnyExerciseProficiency':
                for goal in current_goals:
                    for o in goal.objectives:
                        if isinstance(o, GoalObjectiveAnyExerciseProficiency):
                            return api_invalid_param_response(
                                "User already has a current exercise process goal.")
                objective_descriptors.append(obj)

            if obj['type'] == 'GoalObjectiveAnyVideo':
                for goal in current_goals:
                    for o in goal.objectives:
                        if isinstance(o, GoalObjectiveAnyVideo):
                            return api_invalid_param_response(
                                "User already has a current video process goal.")
                objective_descriptors.append(obj)

            if obj['type'] == 'GoalObjectiveExerciseProficiency':
                obj['exercise'] = models.Exercise.get_by_name(obj['internal_id'])
                if not obj['exercise'] or not obj['exercise'].is_visible_to_current_user():
                    return api_invalid_param_response("Internal error: Could not find exercise.")
                objective_descriptors.append(obj)

            if obj['type'] == 'GoalObjectiveWatchVideo':
                obj['video'] = models.Video.get_for_readable_id(obj['internal_id'])
                if not obj['video']:
                    return api_invalid_param_response("Internal error: Could not find video.")
                user_video = models.UserVideo.get_for_video_and_user_data(obj['video'], user_data)
                if user_video and user_video.completed:
                    return api_invalid_param_response("Video has already been watched.")
                if obj['video'].readable_id in goal_videos:
                    return api_invalid_param_response("Video is already an objective in a current goal.")
                objective_descriptors.append(obj)

    if objective_descriptors:
        objectives = GoalObjective.from_descriptors(objective_descriptors,
            user_data)

        goal = Goal(parent=user_data, title=title, objectives=objectives)
        user_data.save_goal(goal)

        return goal.get_visible_data(None)
    else:
        return api_invalid_param_response("No objectives specified.")


@route("/api/v1/user/goals/<int:id>", methods=["GET"])
@oauth_optional()
@jsonp
@jsonify
def get_user_goal(id):
    user_data = models.UserData.current()
    if not user_data:
        return api_invalid_param_response("User not logged in")

    goal = Goal.get_by_id(id, parent=user_data)

    if not goal:
        return api_invalid_param_response("Could not find goal with ID " + str(id))

    return goal.get_visible_data(None)


@route("/api/v1/user/goals/<int:id>", methods=["PUT"])
@oauth_optional()
@jsonp
@jsonify
def put_user_goal(id):
    user_data = models.UserData.current()
    if not user_data:
        return api_invalid_param_response("User not logged in")

    goal = Goal.get_by_id(id, parent=user_data)

    if not goal:
        return api_invalid_param_response("Could not find goal with ID " + str(id))

    goal_json = request.json

    # currently all you can modify is the title
    if goal_json['title'] != goal.title:
        goal.title = goal_json['title']
        goal.put()

    # or abandon something
    if goal_json.get('abandoned') and not goal.abandoned:
        goal.abandon()
        goal.put()

    return goal.get_visible_data(None)


@route("/api/v1/user/goals/<int:id>", methods=["DELETE"])
@oauth_optional()
@jsonp
@jsonify
def delete_user_goal(id):
    user_data = models.UserData.current()
    if not user_data:
        return api_invalid_param_response("User not logged in")

    goal = Goal.get_by_id(id, parent=user_data)

    if not goal:
        return api_invalid_param_response("Could not find goal with ID " + str(id))

    goal.delete()

    return {}

@route("/api/v1/user/goals", methods=["DELETE"])
@oauth_optional()
@jsonp
@jsonify
def delete_user_goals():
    user_data = models.UserData.current()
    if not user_data.developer:
        return api_unauthorized_response("UNAUTHORIZED")

    user_override = request.request_user_data("email")
    if user_override and user_override.key_email != user_data.key_email:
        user_data = user_override

    GoalList.delete_all_goals(user_data)

    return "Goals deleted"

@route("/api/v1/avatars", methods=["GET"])
@oauth_optional()
@jsonp
@jsonify
def get_avatars():
    """ Returns the list of all avatars bucketed by categories.
    If this is an authenticated request and user-info is available, the
    avatars will be annotated with whether or not they're available.
    """
    user_data = models.UserData.current()
    result = util_avatars.avatars_by_category()
    if user_data:
        for category in result:
            for avatar in category['avatars']:
                avatar.is_available = avatar.is_satisfied_by(user_data)
    return result

@route("/api/v1/dev/version", methods=["GET"])
@jsonp
@jsonify
def get_version_id():
    return { 'version_id' : os.environ['CURRENT_VERSION_ID'] if 'CURRENT_VERSION_ID' in os.environ else None } 

