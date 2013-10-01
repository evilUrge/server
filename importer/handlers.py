# -*- coding: utf-8 -*-

from __future__ import absolute_import, with_statement
import json as json
from collections import defaultdict
import copy

from google.appengine.api import users
from google.appengine.ext import db

from request_handler import RequestHandler
from user_util import dev_server_only
from models import UserData, UserVideo, VideoLog, UserExercise, ProblemLog
from goals.models import Goal
from api.jsonify import jsonify
from api.auth.tests.test import TestOAuthClient
from oauth_provider.oauth import OAuthToken
try:
    import secrets, secrets_dev
except:
    class secrets(object):
        pass
    secrets_dev = secrets

class ImportHandler(RequestHandler):
    """Import data for a particular user to the dev datastore from production.
    Existing data will be overwritten. Please never use this in production!
    Also, don't rely on everything working. Some fields aren't exposed by the
    API, and this simply reads the API. Improvements welcome! :)

    To use this, you need to ensure that secrets.py contains ka_api_consumer_key
    and ka_api_consumer_secret. Also, you need to put your access token in
    secrets_dev.py as ka_api_token_key and ka_api_token_secret. See setup_oauth
    for details.
    """

    access_token = ""
    client = None
    email = ""

    _default_kinds = {
        'UserVideo': 1,
        'VideoLog': 1000,
        'UserExercise': 1,
        'UserExercise': 1,
        'ProblemLog': 1,
        'Goal': 1000,
    }

    @dev_server_only
    def get(self):
        if not hasattr(secrets, 'ka_api_consumer_key') or    \
           not hasattr(secrets, 'ka_api_consumer_secret') or \
           not hasattr(secrets_dev, 'ka_api_token_key') or   \
           not hasattr(secrets_dev, 'ka_api_token_secret'):
            return self.redirect("/")

        self.setup_oauth()

        self.email = self.request_string("email")
        if not self.email:
            raise "Must supply email for user to import"

        params = copy.copy(self._default_kinds)
        params.update(self.request.params)

        # get proper user from addition 1 userexercise
        user_id_json = json.loads(self.api("/api/v1/user/exercises/addition_1"))
        user = users.User(user_id_json['user'])

        # UserData
        user_data_json_raw = self.api("/api/v1/user")
        user_data = UserData.from_json(json.loads(user_data_json_raw), user=user)
        self.output('user_data', user_data, user_data_json_raw)
        user_data.put()

        if 'UserVideo' in params:
            user_videos_json = json.loads(self.api("/api/v1/user/videos"))
            user_videos = []
            for user_video_json in user_videos_json[:params['UserVideo']]:
                user_video = UserVideo.from_json(user_video_json, user_data=user_data)
                user_videos.append(user_video)
                self.output('user_video', user_video, jsonify(user_video_json))

            video_logs = defaultdict(list)
            if 'VideoLog' in params:
                for user_video in user_videos:
                    ytid = user_video.video.youtube_id
                    video_logs_json = json.loads(
                        self.api("/api/v1/user/videos/%s/log" % ytid))
                    for video_log_json in video_logs_json[:params['ProblemLog']]:
                        video_log = VideoLog.from_json(video_log_json, user_video.video, user)
                        video_logs[user_video].append(video_log)
                        self.output("video_log", video_log, jsonify(video_log_json))

                # delete old video logs
                query = VideoLog.all(keys_only=True)
                query.filter('user =', user)
                db.delete(query.fetch(10000))

            db.put(user_videos)
            for k, v in video_logs.iteritems():
                db.put(v)

        if 'UserExercise' in params:
            user_exercises_json = json.loads(self.api("/api/v1/user/exercises"))
            user_exercises = []
            for user_exercise_json in user_exercises_json[:params['UserExercise']]:
                user_exercise = UserExercise.from_json(user_exercise_json, user_data)
                if user_exercise:
                    user_exercises.append(user_exercise)
                    self.output("user_exercise", user_exercise, jsonify(user_exercise_json))

            problem_logs = defaultdict(list)
            if 'ProblemLog' in params:
                for user_exercise in user_exercises:
                    problem_logs_json = json.loads(self.api(
                        "/api/v1/user/exercises/%s/log" % user_exercise.exercise))
                    for problem_log_json in problem_logs_json[:params['ProblemLog']]:
                        problem_log = ProblemLog.from_json(problem_log_json,
                            user_data=user_data,
                            exercise=user_exercise.exercise_model)
                        problem_logs[user_exercise].append(problem_log)
                        self.output("problem_log", problem_log,
                            jsonify(problem_log_json))

            db.put(user_exercises)
            for k, v in problem_logs.iteritems():
                db.put(v)

        if 'Goal' in params:
            with AutoNowDisabled(Goal):
                goals_json = json.loads(self.api("/api/v1/user/goals"))
                goals = []
                for goal_json in goals_json[:params['Goal']]:
                    goal = Goal.from_json(goal_json, user_data=user_data)
                    goals.append(goal)
                    self.output("goal", goal, jsonify(goal_json))

                db.put(goals)

                # need to tell the userdata that it has goals
                user_data.has_current_goals = not all([g.completed for g in goals])
                user_data.put()

    def output(self, name, obj, json_raw):
        self.response.write("//--- %s \n" % name)
        self.response.write(json_raw)
        self.response.write("\n")
        self.response.write(jsonify(obj))
        self.response.write("\n\n")

    def setup_oauth(self, url="http://www.khanacademy.org"):
        self.client = TestOAuthClient(url, secrets.ka_api_consumer_key,
            secrets.ka_api_consumer_secret)

        request_token = OAuthToken(secrets_dev.ka_api_token_key,
            secrets_dev.ka_api_token_secret)
        self.access_token = self.client.fetch_access_token(request_token)

    def api(self, url, email=""):
        email = email or self.email
        if email:
            url += "?email=%s" % email
        return self.client.access_resource(url, self.access_token)

class AutoNowDisabled(object):
    '''ContextManager that temporarily disables auto_now on properties like
    DateTimeProperty. This is useful for importing entites to different
    datastores'''

    def __init__(self, klass):
        self.klass = klass

    def __enter__(self,):
        self.existing = {}
        for name, prop in self.klass.properties().iteritems():
            if hasattr(prop, 'auto_now'):
                self.existing[prop] = prop.auto_now
                prop.auto_now = False
        return self.klass

    def __exit__(self, type, value, traceback):
        for prop, value in self.existing.iteritems():
            prop.auto_now = value
