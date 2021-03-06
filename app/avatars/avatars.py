from util import thousands_separated_number

class Avatar(object):
    """ Base class for data about an avatar that a user can set on her profile.

    Avatars are unlocked by certain achievements, and subclasses can define
    how to unlock specific ones.
    """

    def __init__(self, name, display_name, image_src):
        # Avatar names must be unique.
        self.name = name
        self.display_name = display_name
        self.image_src = image_src

    def is_satisfied_by(self, user_data):
        """ Returns whether or not the user has satisfied the prerequisites
        for using this avatar.

        Subclasses should override based on what they're checking.
        This method should never talk to the datastore.
        """
        return False

class PointsAvatar(Avatar):
    """ A simple avatar that requires the user to have a certain amount
    of energy points before unlocking.
    """

    def __init__(self, name, display_name, image_src, min_points):
        super(PointsAvatar, self).__init__(name, display_name, image_src)
        self.min_points = min_points

    def is_satisfied_by(self, user_data):
        return user_data.points >= self.min_points

class AvatarCategory(object):
    """ A category of Avatars that require similar or identical requirements.
    """

    def __init__(self, title):
        self.title = title

    def filter_avatars(self, avatars):
        """ Returns avatars in the given list that match this category.

        Subclasses should override based on what they're checking.
        This method should never talk to the datastore.
        """
        return []

class AvatarPointsCategory(AvatarCategory):
    """ Builds an AvatarCategory for Avatars that require a number of points
    between min_points (inclusive) and max_points (exclusive).

    If max_points is -1, there is no upper bound.
    """
    def __init__(self, title, min_points, max_points=-1):
        if max_points == -1:
            title = "%s (%s+ points)" % (title,
                                         thousands_separated_number(min_points))
        else:
            title = "%s (%s - %s points)" % (title,
                                             thousands_separated_number(min_points),
                                             thousands_separated_number(max_points))
        super(AvatarPointsCategory, self).__init__(title)
        self.min_points = min_points
        self.max_points = max_points

    def filter_avatars(self, avatars):
        result = []
        for avatar in avatars:
            if not isinstance(avatar, PointsAvatar):
                continue
            points = avatar.min_points
            if (points >= self.min_points and
                    (self.max_points == -1 or points < self.max_points)):
                result.append(avatar)
        return result
