# Badges can either be Exercise badges (can earn one for every Exercise),
# Playlist badges (one for every Playlist),
# Feedback badges (one for every piece of discussion Feedback),
# or context-less which means they can only be earned once.
class BadgeContextType:
    NONE = 0
    EXERCISE = 1
    TOPIC = 2
    FEEDBACK = 3
