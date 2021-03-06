import math

from jinja2.utils import escape

from api import jsonify as apijsonify
from templatefilters import slugify
import models
import shared_jinja
import layer_cache
from models import Exercise


def user_info(username, user_data):
    context = {"username": username, "user_data": user_data}
    return shared_jinja.get().render_template("user_info_only.html", **context)

def column_major_sorted_videos(topic, num_cols=3, column_width=300, gutter=20, font_size=12):
    content = topic.content
    while (len(content) / num_cols < 2) and num_cols > 1:
        num_cols -= 1
    items_in_column = len(content) / num_cols
    remainder = len(content) % num_cols
    link_height = font_size * 1.5
    # Calculate the column indexes (tops of columns). Since video lists won't divide evenly, distribute
    # the remainder to the left-most columns first, and correctly increment the indices for remaining columns
    column_indices = [(items_in_column * multiplier + (multiplier if multiplier <= remainder else remainder)) for multiplier in range(1, num_cols + 1)]


    template_values = {
        "topic": topic,
        "content": content,
        "column_width": column_width,
        "column_indices": column_indices,
        "link_height": link_height,
        "list_height": column_indices[0] * link_height,
    }

    return shared_jinja.get().render_template("column_major_order_videos.html", **template_values)

def exercise_message(exercise, user_exercise_graph, sees_graph=False,
        review_mode=False):
    """Render UserExercise html for APIActionResults["exercise_message_html"] listener in khan-exercise.js.

    This is called **each time** a problem is either attempted or a hint is called (via /api/v1.py)
    returns nothing unless a user is struggling, proficient, etc. then it returns the appropriat template

    See Also: APIActionResults

    sees_graph is part of an ab_test to see if a small graph will help
    """

    # TODO(david): Should we show a message if the user gets a problem wrong
    #     after proficiency, to explain that this exercise needs to be reviewed?

    exercise_states = user_exercise_graph.states(exercise.name)

    if review_mode and user_exercise_graph.has_completed_review():
        filename = 'exercise_message_review_finished.html'

    elif (exercise_states['proficient'] and not exercise_states['reviewing'] and
            not review_mode):
        if sees_graph:
            filename = 'exercise_message_proficient_withgraph.html'
        else:
            filename = 'exercise_message_proficient.html'

    elif exercise_states['struggling']:
        filename = 'exercise_message_struggling.html'
        suggested_prereqs = []
        if exercise.prerequisites:
            proficient_exercises = user_exercise_graph.proficient_exercise_names()
            for prereq in exercise.prerequisites:
                if prereq not in proficient_exercises:
                    prereq_ex = Exercise.get_by_name(prereq)
                    suggested_prereqs.append({
                          'ka_url': prereq_ex.relative_url,
                          'display_name': prereq_ex.display_name,
                          })
        exercise_states['suggested_prereqs'] = apijsonify.jsonify(
                suggested_prereqs)

    else:
        return None

    return shared_jinja.get().render_template(filename, **exercise_states)

def user_points(user_data):
    if user_data:
        points = user_data.points
    else:
        points = 0

    return {"points": points}

def streak_bar(user_exercise_dict):
    progress = user_exercise_dict["progress"]

    bar_max_width = 228
    bar_width = min(1.0, progress) * bar_max_width

    levels = []
    if user_exercise_dict["summative"]:
        c_levels = user_exercise_dict["num_milestones"]
        level_offset = bar_max_width / float(c_levels)
        for ix in range(c_levels - 1):
            levels.append(math.ceil((ix + 1) * level_offset) + 1)

    template_values = {
        "is_suggested": user_exercise_dict["suggested"],
        "is_proficient": user_exercise_dict["proficient"],
        "float_progress": progress,
        "progress": models.UserExercise.to_progress_display(progress),
        "bar_width": bar_width,
        "bar_max_width": bar_max_width,
        "levels": levels
    }

    return shared_jinja.get().render_template("streak_bar.html", **template_values)

@layer_cache.cache_with_key_fxn(lambda browser_id, version_number=None:
    "Templatetags.topic_browser_%s_%s" % (
    browser_id, 
    version_number if version_number else models.Setting.topic_tree_version()))
def topic_browser(browser_id, version_number=None):
    if version_number:
        version = models.TopicVersion.get_by_number(version_number)
    else:
        version = None

    root = models.Topic.get_root(version)
    if not root:
        return ""

    tree = root.make_tree(types = ["Topics"])

    template_values = {
       'browser_id': browser_id, 'topic_tree': tree 
    }

    return shared_jinja.get().render_template("topic_browser.html", **template_values)

def topic_browser_tree(tree, level=0):
    s = ""
    class_name = "topline"
    for child in tree.children:
        href = "#%s" % escape(child.id)
        if not child.children:
            if level == 0:
                s += "<li class='solo'><a href='%s' class='menulink'>%s</a></li>" % (href, escape(child.title))
            else:
                s += "<li class='%s'><a href='%s'>%s</a></li>" % (class_name, href, escape(child.title))
        else:
            if level > 0:
                class_name += " sub"
            s += ("<li class='%s'>"
                        "<a href='%s'>%s</a>"
                            "<ul>" % (class_name, href, escape(child.title)))
            s += topic_browser_tree(child, level=level + 1)
            s += "</ul></li>"

        class_name = ""

    if level == 2:
        s = "<span class='mobile-only'>%s</span>" % s

    return s

def video_name_and_progress(video):
    return "<span class='vid-progress v%d'>%s</span>" % (video.key().id(), escape(video.title))

def jsonify(obj, camel_cased):
    return apijsonify.jsonify(obj, camel_cased=camel_cased)
