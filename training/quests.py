"""Misiones de Fantasy: cada una es un código, una descripción, un premio
en XP, si es semanal (se puede repetir cada semana) o de una sola vez
(para siempre), y una función que dice si `user` la cumple AHORA MISMO.

No hay motor genérico de misiones ni tabla configurable a propósito --
son pocas y fijas, así que están escritas a mano aquí; añadir una nueva
es añadir una entrada a QUESTS con su check().
"""
from datetime import date, timedelta

from django.utils import timezone

ONE_TIME_SENTINEL = date(2000, 1, 1)


def _week_start(today=None):
    today = today or timezone.localdate()
    return today - timedelta(days=today.weekday())


def _check_constancia(user):
    from .models import Workout

    since = _week_start()
    return Workout.objects.filter(user=user, status=Workout.Status.COMPLETED, date__gte=since).count() >= 3


def _check_variedad(user):
    from .services import _muscle_groups_trained_by_username

    since = _week_start()
    counts = _muscle_groups_trained_by_username(since)
    return counts.get(user.username, 0) >= 3


def _check_al_limite(user):
    from .models import SetEntry

    since = _week_start()
    return SetEntry.objects.filter(
        workout_exercise__workout__user=user, workout_exercise__workout__date__gte=since,
        completed=True, rpe__isnull=False,
    ).exists()


def _check_peso_al_dia(user):
    from .models import BodyWeightEntry

    since = _week_start()
    return BodyWeightEntry.objects.filter(user=user, date__gte=since).exists()


def _check_primer_pr(user):
    from .models import PersonalRecord

    return PersonalRecord.objects.filter(user=user).exists()


def _check_diez_entrenamientos(user):
    from .models import Workout

    return Workout.objects.filter(user=user, status=Workout.Status.COMPLETED).count() >= 10


def _check_racha_semanal(user):
    from .services import current_streak_days

    return current_streak_days(user) >= 7


def _check_nutricionista(user):
    from .models import MealEntry

    return MealEntry.objects.filter(user=user).exists()


def _check_sociable(user):
    from accounts.models import friends_of

    return len(friends_of(user)) >= 1


# (code, título, descripción, XP, semanal, check)
QUESTS = [
    ("constancia", "Constancia", "Entrena 3 veces o más en la semana.", 30, True, _check_constancia),
    ("variedad", "Variedad", "Toca 3 grupos musculares distintos en la semana.", 20, True, _check_variedad),
    ("al_limite", "Al límite", "Anota el RPE de alguna serie esta semana.", 10, True, _check_al_limite),
    ("peso_al_dia", "Peso al día", "Registra tu peso corporal esta semana.", 10, True, _check_peso_al_dia),
    ("primer_pr", "Primer récord", "Consigue tu primer PR.", 50, False, _check_primer_pr),
    ("diez_entrenamientos", "Diez entrenamientos", "Completa 10 entrenamientos en total.", 50, False, _check_diez_entrenamientos),
    ("racha_semanal", "Una semana seguida", "Alcanza una racha de 7 días entrenando.", 75, False, _check_racha_semanal),
    ("nutricionista", "Nutricionista", "Registra tu primera comida.", 20, False, _check_nutricionista),
    ("sociable", "Sociable", "Añade a tu primer amigo.", 20, False, _check_sociable),
]

QUESTS_BY_CODE = {q[0]: q for q in QUESTS}


def sync_quests(user):
    """Revisa las misiones que `user` cumple ahora mismo y las apunta si
    todavía no estaban -- se llama al entrar a la página de Fantasy, no
    hace falta ninguna tarea en segundo plano."""
    from .models import QuestCompletion

    this_week = _week_start()
    already = set(
        QuestCompletion.objects.filter(user=user).values_list("quest_code", "period_start")
    )

    newly_completed = []
    for code, title, description, points, weekly, check in QUESTS:
        period = this_week if weekly else ONE_TIME_SENTINEL
        if (code, period) in already:
            continue
        if check(user):
            QuestCompletion.objects.create(user=user, quest_code=code, period_start=period, points=points)
            newly_completed.append((code, title, points))
    return newly_completed
