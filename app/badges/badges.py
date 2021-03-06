# coding=utf8

import util
import models_badges
import phantom_users.util_notify
from notifications import UserNotifier
from badge_context import BadgeContextType

class BadgeCategory(object):
    # Sorted by astronomical size...
    BRONZE = 0 # Meteorite, "Common"
    SILVER = 1 # Moon, "Uncommon"
    GOLD = 2 # Earth, "Rare"
    PLATINUM = 3 # Sun, "Epic"
    DIAMOND = 4 # Black Hole, "Legendary"
    MASTER = 5 # Summative/Academic Achievement

    _serialize_blacklist = [
            "BRONZE", "SILVER", "GOLD",
            "PLATINUM", "DIAMOND", "MASTER",
            ]

    def __init__(self, category):
        self.category = category

    @staticmethod
    def empty_count_dict():
        count_dict = {}
        for category in BadgeCategory.list_categories():
            count_dict[category] = 0
        return count_dict

    @staticmethod
    def all():
        return map(lambda category: BadgeCategory(category),
                   BadgeCategory.list_categories())

    @staticmethod
    def list_categories():
        return [
            BadgeCategory.BRONZE,
            BadgeCategory.SILVER,
            BadgeCategory.GOLD,
            BadgeCategory.PLATINUM,
            BadgeCategory.DIAMOND,
            BadgeCategory.MASTER,
        ]

    @property
    def description(self):
        return BadgeCategory.get_description(self.category)

    @staticmethod
    def get_description(category):
        if category == BadgeCategory.BRONZE:
            return ""+u"מדליות מטאוריט הן שכיחות וקל להשיג אותן כאשר מתחילים."
        elif category == BadgeCategory.SILVER:
            return ""+u"מדליות ירח הן פחות שכיחות ומייצגות השקעה בלימוד."
        elif category == BadgeCategory.GOLD:
            return ""+u"מדליות כדור-ארץ הן נדירות. הן דורשות מידה ניכרת של השקעה בלימוד."
        elif category == BadgeCategory.PLATINUM:
            return ""+u"מדליות שמש הן עצומות. להשיג אותן זהו אתגר אמיתי, והן דורשות התמסרות מרשימה."
        elif category == BadgeCategory.DIAMOND:
            return ""+u"מדליות חור-שחור הן אגדתיות. הן הפרס המיוחד ביותר באקדמיית קהאן."
        elif category == BadgeCategory.MASTER:
            return ""+u"עיטורי משימה הם פרסים מיוחדים המוענקים עבור השלמת משימות תירגול."
        return ""

    @staticmethod
    def get_icon_filename(category):

        name = "half-moon"

        if category == BadgeCategory.BRONZE:
            name = "meteorite"
        elif category == BadgeCategory.SILVER:
            name = "moon"
        elif category == BadgeCategory.GOLD:
            name = "earth"
        elif category == BadgeCategory.PLATINUM:
            name = "sun"
        elif category == BadgeCategory.DIAMOND:
            name = "eclipse"
        elif category == BadgeCategory.MASTER:
            name = "master-challenge-blue"
        
        return name

    @property
    def icon_src(self):
        return BadgeCategory.get_icon_src(self.category)

    @staticmethod
    def get_icon_src(category, suffix="-small"):
        name = BadgeCategory.get_icon_filename(category)
        return util.static_url("/images/badges/%s%s.png" % (name, suffix))

    @property
    def compact_icon_src(self):
        return BadgeCategory.get_compact_icon_src(self.category)

    @staticmethod
    def get_compact_icon_src(category):
        return BadgeCategory.get_icon_src(category, "-60x60")

    @property
    def large_icon_src(self):
        return BadgeCategory.get_large_icon_src(self.category)

    @staticmethod
    def get_large_icon_src(category):
        return BadgeCategory.get_icon_src(category, "")

    @property
    def medium_icon_src(self):
        return BadgeCategory.get_medium_icon_src(self.category)

    @staticmethod
    def get_medium_icon_src(category):
        return BadgeCategory.get_icon_src(category, "-medium")

    @property
    def chart_icon_src(self):
        return BadgeCategory.get_chart_icon_src(self.category)

    @staticmethod
    def get_chart_icon_src(category):
        return BadgeCategory.get_icon_src(category, "-small-chart")

    @property
    def type_label(self):
        return BadgeCategory.get_type_label(self.category)

    @staticmethod
    def get_type_label(category):
        if category == BadgeCategory.BRONZE:
            return ""+u"מטאוריט"
        elif category == BadgeCategory.SILVER:
            return ""+u"ירח"
        elif category == BadgeCategory.GOLD:
            return ""+u"כדור-ארץ"
        elif category == BadgeCategory.PLATINUM:
            return ""+u"שמש"
        elif category == BadgeCategory.DIAMOND:
            return ""+u"חור-שחור"
        elif category == BadgeCategory.MASTER:
            return ""+u"עיטור משימה"
        return ""+u"שכיח"

# Badge is the base class used by various badge subclasses (ExerciseBadge, PlaylistBadge, TimedProblemBadge, etc).
# 
# Each baseclass overrides sets up a couple key pieces of data (description, badge_category, points)
# and implements a couple key functions (is_satisfied_by, is_already_owned_by, award_to, extended_description).
#
# The most important rule to follow with badges is to *never talk to the datastore when checking is_satisfied_by or is_already_owned_by*.
# Many badge calculations need to run every time a user answers a question or watches part of a video, and a couple slow badges can slow down
# the whole system.
# These functions are highly optimized and should only ever use data that is already stored in UserData or is passed as optional keyword arguments
# that have already been calculated / retrieved.
class Badge(object):

    _serialize_whitelist = [
            "points", "badge_category", "description",
            "safe_extended_description", "name", "user_badges", "icon_src",
            "is_owned", "objectives", "can_become_goal", "icons",
            ]

    def __init__(self):
        # Initialized by subclasses:
        #   self.description,
        #   self.badge_category,
        #   self.points

        # Keep .name constant even if description changes.
        # This way we only remove existing badges from people if the class name changes.
        self.name = self.__class__.__name__.lower()
        self.badge_context_type = BadgeContextType.NONE

        # Replace the badge's description with question marks
        # on the "all badges" page if the badge hasn't been achieved yet
        self.is_teaser_if_unknown = False

        # Hide the badge from all badge lists if it hasn't been achieved yet
        self.is_hidden_if_unknown = False

        self.is_owned = False
        
        # A badge may have an associated goal
        self.is_goal = False

    @staticmethod
    def add_target_context_name(name, target_context_name):
        return "%s[%s]" % (name, target_context_name)

    @staticmethod
    def remove_target_context(name_with_context):
        ix = name_with_context.rfind("[")
        if ix >= 0:
            return name_with_context[:ix]
        else:
            return name_with_context

    def category_description(self):
        return BadgeCategory.get_description(self.badge_category)

    @property
    def icon_src(self):
        return BadgeCategory.get_icon_src(self.badge_category)

    @property
    def compact_icon_src(self):
        return BadgeCategory.get_compact_icon_src(self.badge_category)

    @property
    def medium_icon_src(self):
        return BadgeCategory.get_medium_icon_src(self.badge_category)

    @property
    def icons(self):
        return {
                "small": self.icon_src,
                "compact": self.compact_icon_src,
                "medium": self.medium_icon_src,
        }

    def chart_icon_src(self):
        return BadgeCategory.get_chart_icon_src(self.badge_category)

    def type_label(self):
        return BadgeCategory.get_type_label(self.badge_category)

    def name_with_target_context(self, target_context_name):
        if target_context_name is None:
            return self.name
        else:
            return Badge.add_target_context_name(self.name, target_context_name)

    def is_hidden(self):
        return self.is_hidden_if_unknown and not self.is_owned

    def hide_context(self):
        """ Return true if badge shouldn't label the context
        in which it was earned.
        """
        return False

    @property
    def safe_extended_description(self):
        desc = self.extended_description()
        if self.is_teaser_if_unknown and not self.is_owned:
            desc = "???"
        return desc

    # Overridden by individual badge implementations
    def extended_description(self):
        return ""

    # Overridden by individual badge implementations which each grab various parameters from args and kwargs.
    # *args and **kwargs should contain all the data necessary for is_satisfied_by's logic, and implementations
    # should never talk to the datastore or memcache, unless
    # is_manually_awarded returns True
    def is_satisfied_by(self, *args, **kwargs):
        return False

    # Overridden by individual badge implementations which each grab various parameters from args and kwargs
    # *args and **kwargs should contain all the data necessary for is_already_owned_by's logic, and implementations
    # should never talk to the datastore or memcache, unless
    # is_manually_awarded returns True
    def is_already_owned_by(self, user_data, *args, **kwargs):
        return self.name in user_data.badges

    # Overridden by individual badge implementations to indicate whether or
    # not this badge should be awarded through some custom flow that may be
    # potentially expensive, and therefore excluded from checks related to
    # exercise problem attempts or video watching.
    # This should never talk to the datastore or memcache.
    def is_manually_awarded(self):
        return False

    # Calculates target_context and target_context_name from data passed in and calls complete_award_to appropriately.
    #
    # Overridden by individual badge implementations which each grab various parameters from args and kwargs
    # It's ok for award_to to talk to the datastore, because it is run relatively infrequently.
    def award_to(self, user_data, *args, **kwargs):
        self.complete_award_to(user_data)

    # Awards badge to user within given context
    def complete_award_to(self, user_data, target_context=None, target_context_name=None):
        name_with_context = self.name_with_target_context(target_context_name)
        key_name = user_data.key_email + ":" + name_with_context

        if user_data.badges is None:
            user_data.badges = []

        user_data.badges.append(name_with_context)

        user_badge = models_badges.UserBadge.get_by_key_name(key_name)

        if user_badge is None:
            user_data.add_points(self.points)

            user_badge = models_badges.UserBadge(
                    key_name = key_name,
                    user = user_data.user,
                    badge_name = self.name,
                    target_context = target_context,
                    target_context_name = target_context_name,
                    points_earned = self.points)

            user_badge.put()

        # call notifications
        phantom_users.util_notify.update(user_data,None,threshold = False, isProf = False, gotBadge = True)
        UserNotifier.push_badge_for_user_data(user_data, user_badge)

    def frequency(self):
        return models_badges.BadgeStat.count_by_badge_name(self.name)

class GroupedUserBadge(object):
    """ Represents a set of user badges for any particular type. For example,
    it can represent a streak badge that a user earned in multiple exercises.

    This is a transient object that is programmatically computed; it is not
    persisted to the datastore.
    """
    def __init__(self,
                 user=None,
                 badge=None,
                 last_earned_date=None):
        self.user = user
        # The template for the badge type.
        self.badge = badge
        self.last_earned_date = last_earned_date
        # A list of name keys for contexts in which this badge was earned
        # (e.g. the name of the exercise the badge was earned in)
        self.target_context_names = []

    _serialize_blacklist = ["user"]

    @staticmethod
    def build(user, badge, user_badge):
        """ Builds an initial GroupedUserBadge from a single instance.
        Useful to seed building of the group. """
        result = GroupedUserBadge(user=user,
                                  badge=badge,
                                  last_earned_date=user_badge.date)

        target_context_name = None if badge.hide_context() else user_badge.target_context_name

        result.target_context_names.append(target_context_name)
        return result

    @property
    def count(self):
        return len(self.target_context_names)
