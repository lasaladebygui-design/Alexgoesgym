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


def goal_progress(user, goal):
    """Cuánto le falta a `goal` según lo ya registrado -- comparado con
    su mejor 1RM estimado si es un objetivo de PR, con el último peso
    corporal si es de peso, o con los entrenamientos de esta semana si
    es de frecuencia. Devuelve None cuando el objetivo es "personalizado"
    (sin nada objetivo con lo que compararlo) o le falta el dato de
    origen (por ejemplo, un objetivo de PR sin ejercicio elegido)."""
    if goal.kind == goal.Kind.EXERCISE_PR and goal.exercise and goal.target_value_kg:
        current = (
            PersonalRecord.objects.filter(user=user, exercise=goal.exercise, kind=PersonalRecord.Kind.EST_1RM)
            .values_list("value_kg", flat=True).first()
        )
        current = current or Decimal("0")
        return _progress_dict(current, goal.target_value_kg, "kg")

    if goal.kind == goal.Kind.BODYWEIGHT and goal.target_value_kg:
        latest = BodyWeightEntry.objects.filter(user=user).order_by("-date", "-created_at").first()
        if not latest:
            return None
        # El peso puede ser un objetivo de subir O de bajar -- el progreso
        # se mide como distancia recorrida desde el primer registro, no
        # como "más es mejor" a secas.
        first = BodyWeightEntry.objects.filter(user=user).order_by("date", "created_at").first()
        start = first.weight_kg if first else latest.weight_kg
        total_distance = abs(goal.target_value_kg - start)
        covered = abs(latest.weight_kg - start)
        pct = 100 if total_distance == 0 else min(100, round(float(covered / total_distance) * 100))
        return {"current": latest.weight_kg, "target": goal.target_value_kg, "unit": "kg", "pct": pct}

    if goal.kind == goal.Kind.FREQUENCY and goal.target_workouts_per_week:
        today = timezone.localdate()
        week_start = today - timedelta(days=today.weekday())
        current = workouts_since(user, week_start)
        return _progress_dict(current, goal.target_workouts_per_week, "entr./semana")

    return None


def _progress_dict(current, target, unit):
    pct = 100 if not target else min(100, round(float(current) / float(target) * 100))
    return {"current": current, "target": target, "unit": unit, "pct": pct}


# --- Analíticas (training:analytics) ------------------------------------

def muscle_volume_by_week(user, weeks=8):
    """Volumen semanal por grupo muscular (lunes a domingo) -- a
    diferencia de `muscle_groups_recent` (una foto de los últimos 7
    días), esto es la evolución semana a semana: para ver si un grupo
    lleva tiempo sin tocarse, no solo si se tocó la semana pasada."""
    from django.db.models import F

    today = timezone.localdate()
    this_monday = today - timedelta(days=today.weekday())
    first_monday = this_monday - timedelta(weeks=weeks - 1)

    rows = SetEntry.objects.filter(
        workout_exercise__workout__user=user,
        workout_exercise__workout__date__gte=first_monday,
        completed=True, weight_kg__isnull=False, reps_performed__isnull=False,
    ).values(
        "workout_exercise__workout__date",
        "workout_exercise__exercise__primary_muscle__name",
    ).annotate(volume=Sum(F("weight_kg") * F("reps_performed")))

    buckets = {}
    for r in rows:
        muscle = r["workout_exercise__exercise__primary_muscle__name"]
        week_index = (r["workout_exercise__workout__date"] - first_monday).days // 7
        if not (0 <= week_index < weeks):
            continue
        buckets.setdefault(muscle, [Decimal("0")] * weeks)
        buckets[muscle][week_index] += r["volume"]

    labels = [(first_monday + timedelta(weeks=i)).strftime("%d/%m") for i in range(weeks)]
    # Orden por volumen total (de más a menos), para que la leyenda y las
    # capas del gráfico apilado salgan de lo más entrenado a lo menos.
    series = sorted(buckets.items(), key=lambda item: sum(item[1]), reverse=True)
    return labels, series


def muscle_balance(user, days=30):
    """Qué parte del volumen de los últimos `days` días se ha ido a cada
    grupo muscular -- para ver de un vistazo si el reparto está
    equilibrado o si algo se está quedando muy atrás."""
    from django.db.models import F

    since = timezone.localdate() - timedelta(days=days)
    rows = SetEntry.objects.filter(
        workout_exercise__workout__user=user,
        workout_exercise__workout__date__gte=since,
        completed=True, weight_kg__isnull=False, reps_performed__isnull=False,
    ).values("workout_exercise__exercise__primary_muscle__name").annotate(
        volume=Sum(F("weight_kg") * F("reps_performed"))
    ).order_by("-volume")
    return [(r["workout_exercise__exercise__primary_muscle__name"], r["volume"]) for r in rows]


def rpe_trend(user, weeks=8):
    """RPE medio por semana -- si la intensidad percibida sube con el
    tiempo para el mismo tipo de trabajo, suele ser fatiga acumulada
    asomando antes de que se note en el peso que se mueve."""
    from django.db.models import Avg

    today = timezone.localdate()
    this_monday = today - timedelta(days=today.weekday())
    first_monday = this_monday - timedelta(weeks=weeks - 1)

    rows = SetEntry.objects.filter(
        workout_exercise__workout__user=user,
        workout_exercise__workout__date__gte=first_monday,
        completed=True, rpe__isnull=False,
    ).values("workout_exercise__workout__date").annotate(avg_rpe=Avg("rpe"))

    week_values = {i: [] for i in range(weeks)}
    for r in rows:
        week_index = (r["workout_exercise__workout__date"] - first_monday).days // 7
        if 0 <= week_index < weeks:
            week_values[week_index].append(float(r["avg_rpe"]))

    labels = [(first_monday + timedelta(weeks=i)).strftime("%d/%m") for i in range(weeks)]
    values = [round(sum(v) / len(v), 1) if v else None for v in week_values.values()]
    return labels, values


def week_comparison(user):
    """Esta semana (hasta hoy) contra la semana pasada completa --
    volumen, series y entrenamientos, con el cambio en %. `None` cuando
    la semana pasada no tiene con qué comparar (cuenta recién
    estrenada), en vez de un porcentaje sin sentido tipo "+in­finito"."""
    from django.db.models import F

    today = timezone.localdate()
    this_monday = today - timedelta(days=today.weekday())
    last_monday = this_monday - timedelta(weeks=1)

    def stats(start, end):
        qs = SetEntry.objects.filter(
            workout_exercise__workout__user=user,
            workout_exercise__workout__date__gte=start,
            workout_exercise__workout__date__lt=end,
            completed=True,
        )
        volume = qs.filter(weight_kg__isnull=False, reps_performed__isnull=False).aggregate(
            v=Sum(F("weight_kg") * F("reps_performed"))
        )["v"] or Decimal("0")
        workouts = Workout.objects.filter(
            user=user, status=Workout.Status.COMPLETED, date__gte=start, date__lt=end,
        ).count()
        return {"volume": volume, "sets": qs.count(), "workouts": workouts}

    this_week = stats(this_monday, this_monday + timedelta(days=7))
    last_week = stats(last_monday, this_monday)

    def delta_pct(current, previous):
        if not previous:
            return None
        return round((float(current) - float(previous)) / float(previous) * 100)

    return {
        "this": this_week, "last": last_week,
        "volume_delta": delta_pct(this_week["volume"], last_week["volume"]),
        "sets_delta": delta_pct(this_week["sets"], last_week["sets"]),
        "workouts_delta": delta_pct(this_week["workouts"], last_week["workouts"]),
    }


def rep_max_table(user, exercise):
    """A partir del mejor 1RM estimado del ejercicio, cuánto peso
    tocaría para distintos números de repeticiones (fórmula de Epley
    invertida) -- referencia rápida para planificar una serie a un
    número de repeticiones distinto al que dio ese PR. None si el
    ejercicio todavía no tiene ningún 1RM estimado."""
    best_1rm = (
        PersonalRecord.objects.filter(user=user, exercise=exercise, kind=PersonalRecord.Kind.EST_1RM)
        .values_list("value_kg", flat=True).first()
    )
    if not best_1rm:
        return None
    # reps=1 es un caso especial también en la fórmula "de ida"
    # (utils.estimated_1rm): a 1 repetición el peso ES el 1RM, sin pasar
    # por la división -- aplicarla ahí daría 100/(31/30) ≈ 96.8 en vez
    # de 100, inconsistente con cómo se calculó el propio PR.
    return [
        (reps, best_1rm if reps == 1 else round(best_1rm / (Decimal("1") + Decimal(reps) / Decimal("30")), 1))
        for reps in (1, 3, 5, 8, 10, 12)
    ]


# --- Competición (training:competition) ---------------------------------
# Tonnage es para un grupo pequeño de gente que se conoce -- por eso el
# ranking compara a TODO el mundo con cuenta, sin un sistema de amigos
# aparte (nada que pedir ni aceptar): quien se registra ya compite.

def leaderboard_volume_this_week():
    """Volumen total de esta semana, de más a menos."""
    from django.contrib.auth import get_user_model
    from django.db.models import F

    User = get_user_model()
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())

    rows = SetEntry.objects.filter(
        workout_exercise__workout__date__gte=week_start,
        completed=True, weight_kg__isnull=False, reps_performed__isnull=False,
    ).values("workout_exercise__workout__user_id").annotate(
        volume=Sum(F("weight_kg") * F("reps_performed"))
    )
    by_user = {r["workout_exercise__workout__user_id"]: r["volume"] for r in rows}
    usernames = dict(User.objects.filter(pk__in=by_user).values_list("pk", "username"))
    ranked = sorted(by_user.items(), key=lambda item: item[1], reverse=True)
    return [(usernames[uid], volume) for uid, volume in ranked]


def leaderboard_workouts_this_week():
    """Entrenamientos completados esta semana, de más a menos."""
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    rows = (
        Workout.objects.filter(status=Workout.Status.COMPLETED, date__gte=week_start)
        .values("user__username").annotate(n=Count("id")).order_by("-n")
    )
    return [(r["user__username"], r["n"]) for r in rows]


def leaderboard_streaks():
    """Racha de días consecutivos entrenando, de más a menos -- reutiliza
    current_streak_days por persona (son pocas cuentas, no compensa una
    consulta SQL más compleja solo para esto)."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    rows = [(u.username, current_streak_days(u)) for u in User.objects.all()]
    rows = [row for row in rows if row[1] > 0]
    return sorted(rows, key=lambda row: row[1], reverse=True)
