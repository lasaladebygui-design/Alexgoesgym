"""Cálculos compartidos por el dashboard y las vistas de entrenamiento --
todo lo que no es un CRUD directo de un modelo vive aquí para no repetir
lógica de agregación entre vistas."""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone

from .models import BodyWeightEntry, PersonalRecord, SetEntry, Workout


def current_workout(user):
    return Workout.objects.filter(user=user, status=Workout.Status.IN_PROGRESS).order_by("-start_time").first()


def exercises_picker_data(user):
    """Catálogo de ejercicios visible para `user`, en la forma que espera
    el buscador de ejercicio (ver training/_exercise_picker.html): un
    JSON ligero con id/nombre/músculo y un campo `search` ya en
    minúsculas y sin tildes, para filtrar al teclear sin ir al
    servidor -- con 100+ ejercicios en el catálogo, hace falta algo más
    cómodo que un <select> nativo."""
    import unicodedata

    from .forms import visible_exercises_q
    from .models import Exercise

    def normalize(text):
        stripped = unicodedata.normalize("NFKD", text)
        return "".join(ch for ch in stripped if not unicodedata.combining(ch)).lower()

    exercises = Exercise.objects.filter(visible_exercises_q(user), is_active=True).select_related("primary_muscle").order_by("name")
    return [
        {
            "id": ex.pk, "name": ex.name, "muscle": ex.primary_muscle.name,
            "search": normalize(f"{ex.name} {ex.primary_muscle.name}"),
        }
        for ex in exercises
    ]


def recent_exercises(user, limit=8):
    """Los últimos ejercicios distintos que se han usado -- para
    ofrecerlos como chips de un toque encima del buscador (ver
    _exercise_picker.html): lo más cómodo es no tener ni que escribir
    para el ejercicio de siempre."""
    from .models import Exercise, WorkoutExercise

    seen = []
    seen_ids = set()
    qs = (
        WorkoutExercise.objects.filter(workout__user=user)
        .select_related("exercise")
        .order_by("-workout__start_time")[:60]
    )
    for we in qs:
        if we.exercise_id not in seen_ids:
            seen_ids.add(we.exercise_id)
            seen.append(we.exercise)
        if len(seen) >= limit:
            break
    return seen


def last_workout(user):
    return Workout.objects.filter(user=user, status=Workout.Status.COMPLETED).order_by("-start_time").first()


def next_routine_day(user):
    """El siguiente día "que toca" -- el que va después del último que se
    hizo, dentro de la rutina activa, dando la vuelta al llegar al final.
    Sin rutina activa (o sin ningún entrenamiento previo hecho desde
    ella) no hay "próximo" que adivinar."""
    from .models import Routine

    routine = Routine.objects.filter(user=user, is_active=True).first()
    if not routine:
        return None
    days = list(routine.days.all())
    if not days:
        return None
    last = Workout.objects.filter(user=user, routine=routine, routine_day__isnull=False).order_by("-start_time").first()
    if not last or not last.routine_day:
        return days[0]
    ids = [d.pk for d in days]
    try:
        idx = ids.index(last.routine_day_id)
    except ValueError:
        return days[0]
    return days[(idx + 1) % len(days)]


def bodyweight_now(user):
    return BodyWeightEntry.objects.filter(user=user).order_by("-date", "-created_at").first()


def bodyweight_trend(user, days=90):
    since = timezone.localdate() - timedelta(days=days)
    return list(
        BodyWeightEntry.objects.filter(user=user, date__gte=since).order_by("date").values("date", "weight_kg")
    )


def volume_since(user, since_date):
    from django.db.models import F

    total = SetEntry.objects.filter(
        workout_exercise__workout__user=user,
        workout_exercise__workout__date__gte=since_date,
        completed=True, weight_kg__isnull=False, reps_performed__isnull=False,
    ).aggregate(total=Sum(F("weight_kg") * F("reps_performed")))["total"]
    return total or Decimal("0")


def sets_since(user, since_date):
    return SetEntry.objects.filter(
        workout_exercise__workout__user=user,
        workout_exercise__workout__date__gte=since_date,
    ).count()


def weekly_volume_series(user, weeks=12):
    """Volumen total por semana (lunes a domingo) de las últimas `weeks`
    semanas, incluida la actual -- para el gráfico de tendencia del
    dashboard. Se agrupa en Python en vez de con TruncWeek porque son
    pocos registros y así se evita depender de que la semana ISO de la
    base de datos coincida con "lunes primero" en todos los motores."""
    from django.db.models import F

    today = timezone.localdate()
    this_monday = today - timedelta(days=today.weekday())
    first_monday = this_monday - timedelta(weeks=weeks - 1)

    rows = SetEntry.objects.filter(
        workout_exercise__workout__user=user,
        workout_exercise__workout__date__gte=first_monday,
        completed=True, weight_kg__isnull=False, reps_performed__isnull=False,
    ).values("workout_exercise__workout__date").annotate(
        volume=Sum(F("weight_kg") * F("reps_performed")),
    )
    by_date = {r["workout_exercise__workout__date"]: r["volume"] for r in rows}

    buckets = [Decimal("0")] * weeks
    for date, volume in by_date.items():
        week_index = (date - first_monday).days // 7
        if 0 <= week_index < weeks:
            buckets[week_index] += volume

    labels = [(first_monday + timedelta(weeks=i)).strftime("%d/%m") for i in range(weeks)]
    return labels, buckets


def session_volume_series(user, exercise, sessions=15):
    """Volumen total por sesión (entrenamiento) de un ejercicio, las
    últimas `sessions` veces que ha aparecido -- para comparar con la
    gráfica de 1RM estimado en la ficha del ejercicio: a veces se sube
    de peso pero se baja de volumen (menos series/reps), y solo el 1RM
    no lo enseña."""
    from django.db.models import F

    rows = (
        SetEntry.objects.filter(
            workout_exercise__workout__user=user, workout_exercise__exercise=exercise,
            completed=True, weight_kg__isnull=False, reps_performed__isnull=False,
        )
        .values("workout_exercise__workout__date")
        .annotate(volume=Sum(F("weight_kg") * F("reps_performed")))
        .order_by("-workout_exercise__workout__date")[:sessions]
    )
    rows = list(reversed(rows))
    return (
        [r["workout_exercise__workout__date"] for r in rows],
        [r["volume"] for r in rows],
    )


def workouts_since(user, since_date):
    return Workout.objects.filter(user=user, status=Workout.Status.COMPLETED, date__gte=since_date).count()


def total_time_seconds(user):
    workouts = Workout.objects.filter(user=user, status=Workout.Status.COMPLETED, end_time__isnull=False)
    return sum((w.end_time - w.start_time).total_seconds() for w in workouts)


def recent_prs(user, limit=6):
    return PersonalRecord.objects.filter(user=user).select_related("exercise").order_by("-achieved_at")[:limit]


def current_streak_days(user):
    """Días consecutivos (contando desde hoy o ayer) con al menos un
    entrenamiento completado."""
    dates = set(
        Workout.objects.filter(user=user, status=Workout.Status.COMPLETED).values_list("date", flat=True)
    )
    if not dates:
        return 0
    today = timezone.localdate()
    cursor = today if today in dates else today - timedelta(days=1)
    if cursor not in dates:
        return 0
    streak = 0
    while cursor in dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def muscle_groups_recent(user, days=7):
    """Grupos musculares principales entrenados en los últimos N días,
    con cuántas series se les han dedicado -- para el "qué he tocado
    últimamente" del dashboard."""
    since = timezone.localdate() - timedelta(days=days)
    rows = (
        SetEntry.objects.filter(
            workout_exercise__workout__user=user,
            workout_exercise__workout__date__gte=since,
            completed=True,
        )
        .values("workout_exercise__exercise__primary_muscle__name")
        .annotate(sets=Count("id"))
        .order_by("-sets")
    )
    return [(r["workout_exercise__exercise__primary_muscle__name"], r["sets"]) for r in rows]


def strength_progression(user, exercise, days=180):
    """Serie temporal del 1RM estimado más alto de cada entrenamiento en
    el que ha aparecido el ejercicio -- lo que pinta el gráfico de
    "evolución de fuerza" de la ficha de un ejercicio."""
    from django.db.models import Max

    since = timezone.localdate() - timedelta(days=days)
    rows = (
        SetEntry.objects.filter(
            workout_exercise__workout__user=user,
            workout_exercise__exercise=exercise,
            workout_exercise__workout__date__gte=since,
            completed=True, estimated_1rm_kg__isnull=False,
        )
        .values("workout_exercise__workout__date")
        .annotate(best=Max("estimated_1rm_kg"))
        .order_by("workout_exercise__workout__date")
    )
    return [(r["workout_exercise__workout__date"], r["best"]) for r in rows]
