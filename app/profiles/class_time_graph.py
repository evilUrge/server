import datetime
import time
import logging

from google.appengine.api import users

import models
import classtime
import util

def class_time_graph_context(user_data, dt_utc, tz_offset, student_list):

    if not user_data:
        return {}
    
    students_data = None
    if student_list:
        students_data = student_list.get_students_data()
    else:
        students_data = user_data.get_students_data()

    students_data = sorted(students_data, key=lambda student: student.nickname)
    classtime_table = None
    classtime_analyzer = classtime.ClassTimeAnalyzer(tz_offset)
    graph_data = []

    if classtime_analyzer.timezone_offset != -1:
        # If no timezone offset is specified, don't bother grabbing all the data
        # because we'll be redirecting back to here w/ timezone information.
        try:
            classtime_table = classtime_analyzer.get_classtime_table_by_coach(user_data, students_data, dt_utc)
        except Exception, e:
            logging.exception("caught error in calculating report")
            classtime_table = classtime_analyzer.get_classtime_table_old(students_data, dt_utc)


    profiles = []
    for user_data_student in students_data:

        short_name = user_data_student.nickname
        if len(short_name) > 18:
            short_name = short_name[0:18] + "..."

        total_student_minutes = 0
        if classtime_table is not None:
            total_student_minutes = classtime_table.get_student_total(user_data_student.email)


        profiles.append(user_data_student.profile_root)
        graph_data.append({
            "name": short_name,
            "total_minutes": "~%.0f" % total_student_minutes
            })

    return {
            "profiles": map(str, profiles),
            "classtime_table": classtime_table,
            "coach_email": user_data.email,
            "width": (60 * len(graph_data)) + 120,
            "graph_data": graph_data,
            "is_graph_empty": len(classtime_table.rows) <= 0,
            "user_data_students": students_data,
            "c_points": reduce(lambda a, b: a + b, map(lambda s: s.points, students_data), 0)
        }

