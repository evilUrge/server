# coding=utf8

import models
from badges import Badge, BadgeCategory
import json

# All badges awarded for completing some subset of exercises inherit from ExerciseCompletionBadge
class ExerciseCompletionBadge(Badge):

    def __init__(self):
        super(ExerciseCompletionBadge, self).__init__()
        self.is_goal = True

    def is_satisfied_by(self, *args, **kwargs):
        user_data = kwargs.get("user_data", None)
        if user_data is None:
            return False

        if len(self.exercise_names_required) <= 0:
            return False

        for exercise_name in self.exercise_names_required:
            if not user_data.is_proficient_at(exercise_name):
                return False

        return True

    def goal_objectives(self):
        if self.exercise_names_required:
            return json.dumps(self.exercise_names_required)
        return json.dumps([])

    def extended_description(self):
        badges = []
        total_len = 0

        for exercise_name in self.exercise_names_required:
            ex = models.Exercise.get_by_name(exercise_name)
            long_name = ex.display_name
            short_name = ex.short_name

            display_name = long_name if (total_len < 80) else short_name

            badges.append(display_name)
            total_len += len(display_name)

        s_exercises = ", ".join(badges)

        return u"השיגו מיומנות ב%s" % s_exercises

class ChallengeCompletionBadge(ExerciseCompletionBadge):

    def __init__(self):
        super(ChallengeCompletionBadge, self).__init__()
        self.is_goal = False

    def extended_description(self):
        s_exercises = ""
        for exercise_name in self.exercise_names_required:
            if len(s_exercises) > 0:
                s_exercises += ", "
            s_exercises += models.Exercise.to_display_name(exercise_name)
        return u"השלימו את %s" % s_exercises

    @property
    def compact_icon_src(self):
        return self.icon_src

class LevelOneArithmeticianBadge(ExerciseCompletionBadge):
    def __init__(self):
        ExerciseCompletionBadge.__init__(self)
        self.exercise_names_required = ['addition_1', 'subtraction_1', 'multiplication_1', 'division_1']
        self.description = ""+u"שולית חישוב"
        self.badge_category = BadgeCategory.SILVER
        self.points = 100

class LevelTwoArithmeticianBadge(ExerciseCompletionBadge):
    def __init__(self):
        ExerciseCompletionBadge.__init__(self)
        self.exercise_names_required = ['addition_4', 'subtraction_4', 'multiplication_4', 'division_4']
        self.description = ""+u"אומן חשבון"
        self.badge_category = BadgeCategory.SILVER
        self.points = 500

class LevelThreeArithmeticianBadge(ExerciseCompletionBadge):
    def __init__(self):
        ExerciseCompletionBadge.__init__(self)
        self.exercise_names_required = ['multiplying_decimals', 'dividing_decimals', 'multiplying_fractions', 'dividing_fractions']
        self.description = ""+u"אמן חישוב"
        self.badge_category = BadgeCategory.SILVER
        self.points = 750

class TopLevelArithmeticianBadge(ChallengeCompletionBadge):
    def __init__(self):
        ChallengeCompletionBadge.__init__(self)
        self.exercise_names_required = ['arithmetic_challenge']
        self.description = ""+u"רב-אמן חישוב"
        self.badge_category = BadgeCategory.MASTER
        self.points = 10000
    
    @property
    def icon_src(self):
        return "/images/badges/Arithmetic.png"

class LevelOneTrigonometricianBadge(ExerciseCompletionBadge):
    def __init__(self):
        ExerciseCompletionBadge.__init__(self)
        self.exercise_names_required = ['angles_2', 'distance_formula', 'pythagorean_theorem_1']
        self.description = ""+u"שוליה טריגונומטריקאי"
        self.badge_category = BadgeCategory.SILVER
        self.points = 100

class LevelTwoTrigonometricianBadge(ExerciseCompletionBadge):
    def __init__(self):
        ExerciseCompletionBadge.__init__(self)
        self.exercise_names_required = ['pythagorean_theorem_2', 'trigonometry_1']
        self.description = ""+u"אומן טריגונומטריקאי"
        self.badge_category = BadgeCategory.SILVER
        self.points = 500

class LevelThreeTrigonometricianBadge(ExerciseCompletionBadge):
    def __init__(self):
        ExerciseCompletionBadge.__init__(self)
        self.exercise_names_required = ['trigonometry_2', 'graphs_of_sine_and_cosine', 'inverse_trig_functions', 'trig_identities_1']
        self.description = ""+u"אמן טריגונומטריקאי"
        self.badge_category = BadgeCategory.SILVER
        self.points = 750

class TopLevelTrigonometricianBadge(ChallengeCompletionBadge):
    def __init__(self):
        ChallengeCompletionBadge.__init__(self)
        self.exercise_names_required = ['trigonometry_challenge']
        self.description = ""+u"רב-אמן טריגונומטריקאי"
        self.badge_category = BadgeCategory.MASTER
        self.points = 10000
    
    @property
    def icon_src(self):
        return "/images/badges/Geometry-Trig.png"

class LevelOnePrealgebraistBadge(ExerciseCompletionBadge):
    def __init__(self):
        ExerciseCompletionBadge.__init__(self)
        self.exercise_names_required = ['exponents_1', 'adding_and_subtracting_negative_numbers', 'adding_and_subtracting_fractions']
        self.description = ""+u"שולית קדם-אלגברה"
        self.badge_category = BadgeCategory.SILVER
        self.points = 100

class LevelTwoPrealgebraistBadge(ExerciseCompletionBadge):
    def __init__(self):
        ExerciseCompletionBadge.__init__(self)
        self.exercise_names_required = ['exponents_2', 'multiplying_and_dividing_negative_numbers', 'multiplying_fractions', 'dividing_fractions']
        self.description = ""+u"אומן קדם-אלגברה"
        self.badge_category = BadgeCategory.SILVER
        self.points = 500

class LevelThreePrealgebraistBadge(ExerciseCompletionBadge):
    def __init__(self):
        ExerciseCompletionBadge.__init__(self)
        self.exercise_names_required = ['exponents_3', 'order_of_operations', 'ordering_numbers', 'scientific_notation', 'units', 'simplifying_radicals']
        self.description = ""+u"אמן קדם-אלגברה"
        self.badge_category = BadgeCategory.SILVER
        self.points = 750

class TopLevelPrealgebraistBadge(ChallengeCompletionBadge):
    def __init__(self):
        ChallengeCompletionBadge.__init__(self)
        self.exercise_names_required = ['pre-algebra_challenge']
        self.description = ""+u"רב-אמן קדם-אלגברה"
        self.badge_category = BadgeCategory.MASTER
        self.points = 10000
    
    @property
    def icon_src(self):
        return "/images/badges/Pre-Algebra.png"

class LevelOneAlgebraistBadge(ExerciseCompletionBadge):
    def __init__(self):
        ExerciseCompletionBadge.__init__(self)
        self.exercise_names_required = ['exponents_3', 'exponent_rules', 'logarithms_1', 'linear_equations_1', 'percentage_word_problems_1', 'functions_1']
        self.description = ""+u"שולית קדם-אלגברה"
        self.badge_category = BadgeCategory.SILVER
        self.points = 100

class LevelTwoAlgebraistBadge(ExerciseCompletionBadge):
    def __init__(self):
        ExerciseCompletionBadge.__init__(self)
        self.exercise_names_required = ['linear_equations_2', 'percentage_word_problems_2', 'functions_2', 'domain_of_a_function', 'even_and_odd_functions', 'shifting_and_reflecting_functions']
        self.description = ""+u"אומן קדם-אלגברה"
        self.badge_category = BadgeCategory.SILVER
        self.points = 500

class LevelThreeAlgebraistBadge(ExerciseCompletionBadge):
    def __init__(self):
        ExerciseCompletionBadge.__init__(self)
        self.exercise_names_required = ['linear_equations_3', 'systems_of_equations', 'multiplying_expressions_1', 'even_and_odd_functions', 'inverses_of_functions', 'slope_of_a_line', 'midpoint_formula', 'line_relationships', 'functions_3']
        self.description = ""+u"אמן קדם-אלגברה ראשוני"
        self.badge_category = BadgeCategory.SILVER
        self.points = 750

class LevelFourAlgebraistBadge(ExerciseCompletionBadge):
    def __init__(self):
        ExerciseCompletionBadge.__init__(self)
        self.exercise_names_required = ['linear_equations_4', 'linear_inequalities', 'average_word_problems', 'equation_of_a_line', 'solving_quadratics_by_factoring', 'quadratic_equation', 'solving_for_a_variable', 'expressions_with_unknown_variables']
        self.description = ""+u"אמן קדם-אלגברה מתקדם"
        self.badge_category = BadgeCategory.SILVER
        self.points = 1000
        
class LevelFiveAlgebraistBadge(ExerciseCompletionBadge):
    def __init__(self):
        ExerciseCompletionBadge.__init__(self)
        self.exercise_names_required = ['new_definitions_1', 'new_definitions_2', 'expressions_with_unknown_variables_2', 'absolute_value_equations', 'radical_equations', 'rate_problems_1']
        self.description = ""+u"אמן קדם-אלגברה מוביל"
        self.badge_category = BadgeCategory.SILVER
        self.points = 1000

class TopLevelAlgebraistBadge(ChallengeCompletionBadge):
    def __init__(self):
        ChallengeCompletionBadge.__init__(self)
        self.exercise_names_required = ['algebra_challenge']
        self.description = ""+u"רב-אמן אלגברה"
        self.badge_category = BadgeCategory.MASTER
        self.points = 10000
    
    @property
    def icon_src(self):
        return "/images/badges/Algebra.png"
