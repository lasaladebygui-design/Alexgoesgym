import json
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    BodyWeightEntryForm,
    GoalForm,
    RoutineDayForm,
    RoutineExerciseForm,
    RoutineForm,
    SetEntryForm,
    WorkoutExerciseAddForm,
    WorkoutFinishForm,
    WorkoutStartForm,
    visible_exercises_q,
)
from .models import (
    BodyWeightEntry,
    Exercise,
    Goal,
    PersonalRecord,
    Routine,
    RoutineDay,
    RoutineExercise,
    SetEntry,
    Workout,
    WorkoutExercise,
)
from .services import exercises_picker_data, recent_exercises, strength_progression


# --- Registro de entrenamiento (la función principal) -----------------------

@login_required
def workout_start(request):
    if request.method == "POST":
        form = WorkoutStartForm(request.POST, user=request.user)
        if form.is_valid():
            routine_day = form.cleaned_data["routine_day"]
            name = form.cleaned_data["name"] or (routine_day.name if routine_day else "Entrenamiento libre")
            workout = Workout.objects.create(
                user=request.user, routine=routine_day.routine if routine_day else None,
                routine_day=routine_day, name=name, date=timezone.localdate(), start_time=timezone.now(),
            )
            if routine_day:
                for i, re in enumerate(routine_day.exercises.select_related("exercise")):
                    WorkoutExercise.objects.create(
                        workout=workout, exercise=re.exercise, order=i, superset_group=re.superset_group,
                    )
            return redirect("training:workout-session", pk=workout.pk)
    else:
        form = WorkoutStartForm(user=request.user)
    routine_days = RoutineDay.objects.filter(routine__user=request.user, routine__is_active=True).select_related("routine")
    return render(request, "training/workout_start.html", {"form": form, "routine_days": routine_days})


@login_required
def workout_session(request, pk):
    workout = get_object_or_404(Workout, pk=pk, user=request.user)
    if workout.status != Workout.Status.IN_PROGRESS:
        return redirect("training:workout-detail", pk=pk)
    exercises = workout.exercises.select_related("exercise", "exercise__primary_muscle").prefetch_related("sets")

    rows = []
    for we in exercises:
        sets = list(we.sets.all())
        last = sets[-1] if sets else None
        initial = {"set_type": SetEntry.SetType.WORKING, "unit": request.user.unit_preference}
        if last:
            initial.update({
                "weight": last.weight_display, "unit": last.input_unit, "set_type": last.set_type,
                "reps_target": last.reps_target, "rpe": last.rpe, "rir": last.rir,
            })
        set_rows = [
            {
                "set": s,
                "edit_form": SetEntryForm(instance=s, initial={"weight": s.weight_display, "unit": s.input_unit}),
            }
            for s in sets
        ]
        repeat = None
        if last:
            # Valores planos (str, formato "de máquina") para el botón
            # "Repetir última" -- se rellenan en Python, no en la plantilla,
            # para no depender de cómo el locale (es-ES, coma decimal)
            # formatearía un Decimal si se imprimiera directamente.
            repeat = {
                "set_type": last.set_type,
                "weight": str(last.weight_display) if last.weight_display is not None else "",
                "unit": last.input_unit,
                "reps_performed": last.reps_performed if last.reps_performed is not None else "",
                "reps_target": last.reps_target if last.reps_target is not None else "",
                "rpe": str(last.rpe) if last.rpe is not None else "",
                "rir": last.rir if last.rir is not None else "",
            }
        rows.append({
            "we": we, "set_rows": set_rows, "repeat": repeat,
            "add_form": SetEntryForm(initial=initial),
            "volume": we.total_volume_kg,
        })

    add_exercise_form = WorkoutExerciseAddForm(user=request.user)
    finish_form = WorkoutFinishForm(instance=workout)
    return render(request, "training/workout_session.html", {
        "workout": workout, "rows": rows,
        "add_exercise_form": add_exercise_form, "finish_form": finish_form,
        "exercises_json": json.dumps(exercises_picker_data(request.user)),
        "recent_picks": recent_exercises(request.user),
    })


@login_required
def workout_exercise_add(request, pk):
    workout = get_object_or_404(Workout, pk=pk, user=request.user)
    if request.method == "POST":
        form = WorkoutExerciseAddForm(request.POST, user=request.user)
        if form.is_valid():
            order = workout.exercises.count()
            WorkoutExercise.objects.create(
                workout=workout, exercise=form.cleaned_data["exercise"],
                order=order, superset_group=form.cleaned_data["superset_group"],
            )
        else:
            messages.error(request, "No se pudo añadir el ejercicio: elige uno de la lista.")
    return redirect("training:workout-session", pk=pk)


@login_required
def workout_exercise_delete(request, pk, we_pk):
    workout = get_object_or_404(Workout, pk=pk, user=request.user)
    if request.method == "POST":
        get_object_or_404(WorkoutExercise, pk=we_pk, workout=workout).delete()
    return redirect("training:workout-session", pk=pk)


@login_required
def set_add(request, pk, we_pk):
    workout = get_object_or_404(Workout, pk=pk, user=request.user)
    workout_exercise = get_object_or_404(WorkoutExercise, pk=we_pk, workout=workout)
    if request.method == "POST":
        form = SetEntryForm(request.POST)
        if form.is_valid():
            set_entry = form.save(commit=False)
            set_entry.workout_exercise = workout_exercise
            set_entry.set_number = workout_exercise.sets.count() + 1
            set_entry.save()
        else:
            messages.error(request, "No se pudo guardar la serie: revisa los datos.")
    return redirect("training:workout-session", pk=pk)


@login_required
def set_edit(request, pk, set_pk):
    workout = get_object_or_404(Workout, pk=pk, user=request.user)
    set_entry = get_object_or_404(SetEntry, pk=set_pk, workout_exercise__workout=workout)
    if request.method == "POST":
        form = SetEntryForm(request.POST, instance=set_entry)
        if form.is_valid():
            form.save()
        else:
            messages.error(request, "No se pudo guardar la serie: revisa los datos.")
    return redirect("training:workout-session", pk=pk)


@login_required
def set_delete(request, pk, set_pk):
    workout = get_object_or_404(Workout, pk=pk, user=request.user)
    set_entry = get_object_or_404(SetEntry, pk=set_pk, workout_exercise__workout=workout)
    if request.method == "POST":
        we = set_entry.workout_exercise
        set_entry.delete()
        for i, s in enumerate(we.sets.order_by("set_number"), start=1):
            if s.set_number != i:
                s.set_number = i
                s.save(update_fields=["set_number"])
    return redirect("training:workout-session", pk=pk)


@login_required
def workout_finish(request, pk):
    workout = get_object_or_404(Workout, pk=pk, user=request.user)
    if request.method == "POST":
        form = WorkoutFinishForm(request.POST, instance=workout)
        if form.is_valid():
            workout = form.save(commit=False)
            workout.finish()
            messages.success(request, f"«{workout.name}» completado. ¡Buen trabajo!")
            return redirect("training:workout-detail", pk=pk)
    return redirect("training:workout-session", pk=pk)


@login_required
def workout_cancel(request, pk):
    workout = get_object_or_404(Workout, pk=pk, user=request.user)
    if request.method == "POST":
        workout.status = Workout.Status.CANCELLED
        workout.end_time = timezone.now()
        workout.save(update_fields=["status", "end_time"])
    return redirect("training:workout-history")


@login_required
def workout_history(request):
    workouts = Workout.objects.filter(user=request.user).exclude(status=Workout.Status.IN_PROGRESS).select_related("routine_day")
    page_obj = Paginator(workouts, 20).get_page(request.GET.get("page"))
    return render(request, "training/workout_history.html", {"page_obj": page_obj})


@login_required
def workout_detail(request, pk):
    workout = get_object_or_404(Workout, pk=pk, user=request.user)
    if workout.status == Workout.Status.IN_PROGRESS:
        return redirect("training:workout-session", pk=pk)
    exercises = workout.exercises.select_related("exercise").prefetch_related("sets")
    return render(request, "training/workout_detail.html", {"workout": workout, "exercises": exercises})


@login_required
def workout_repeat(request, pk):
    """Un clic para volver a entrenar lo mismo: crea una sesión nueva con
    los MISMOS ejercicios (mismo orden, mismas superseries) que `pk`,
    pero sin series -- se registran de cero, la comodidad está en no
    tener que volver a buscar y añadir cada ejercicio uno a uno."""
    source = get_object_or_404(Workout, pk=pk, user=request.user)
    if request.method != "POST":
        return redirect("training:workout-detail", pk=pk)

    workout = Workout.objects.create(
        user=request.user, routine=source.routine, routine_day=source.routine_day,
        name=source.name, date=timezone.localdate(), start_time=timezone.now(),
    )
    for we in source.exercises.order_by("order"):
        WorkoutExercise.objects.create(
            workout=workout, exercise=we.exercise, order=we.order, superset_group=we.superset_group,
        )
    return redirect("training:workout-session", pk=workout.pk)


# --- Rutinas -----------------------------------------------------------------

@login_required
def routine_list(request):
    routines = Routine.objects.filter(user=request.user).prefetch_related("days")
    return render(request, "training/routine_list.html", {"routines": routines})


@login_required
def routine_create(request):
    if request.method == "POST":
        form = RoutineForm(request.POST)
        if form.is_valid():
            routine = form.save(commit=False)
            routine.user = request.user
            routine.save()
            return redirect("training:routine-detail", pk=routine.pk)
    else:
        form = RoutineForm()
    return render(request, "training/routine_form.html", {"form": form})


@login_required
def routine_detail(request, pk):
    routine = get_object_or_404(Routine.objects.prefetch_related("days__exercises__exercise"), pk=pk, user=request.user)
    day_form = RoutineDayForm()
    re_form = RoutineExerciseForm(user=request.user, initial={"target_sets": 3})
    return render(request, "training/routine_detail.html", {
        "routine": routine, "day_form": day_form, "re_form": re_form,
        "exercises_json": json.dumps(exercises_picker_data(request.user)),
    })


@login_required
def routine_delete(request, pk):
    routine = get_object_or_404(Routine, pk=pk, user=request.user)
    if request.method == "POST":
        routine.delete()
        messages.success(request, f"«{routine.name}» eliminada.")
    return redirect("training:routine-list")


@login_required
def routine_day_add(request, pk):
    routine = get_object_or_404(Routine, pk=pk, user=request.user)
    if request.method == "POST":
        form = RoutineDayForm(request.POST)
        if form.is_valid():
            day = form.save(commit=False)
            day.routine = routine
            day.order = routine.days.count()
            day.save()
    return redirect("training:routine-detail", pk=pk)


@login_required
def routine_day_delete(request, pk, day_pk):
    routine = get_object_or_404(Routine, pk=pk, user=request.user)
    if request.method == "POST":
        get_object_or_404(RoutineDay, pk=day_pk, routine=routine).delete()
    return redirect("training:routine-detail", pk=pk)


@login_required
def routine_exercise_add(request, pk, day_pk):
    routine = get_object_or_404(Routine, pk=pk, user=request.user)
    day = get_object_or_404(RoutineDay, pk=day_pk, routine=routine)
    if request.method == "POST":
        form = RoutineExerciseForm(request.POST, user=request.user)
        if form.is_valid():
            re = form.save(commit=False)
            re.routine_day = day
            re.save()
        else:
            messages.error(request, "No se pudo añadir el ejercicio: revisa los datos.")
    return redirect("training:routine-detail", pk=pk)


@login_required
def routine_exercise_delete(request, pk, day_pk, re_pk):
    routine = get_object_or_404(Routine, pk=pk, user=request.user)
    day = get_object_or_404(RoutineDay, pk=day_pk, routine=routine)
    if request.method == "POST":
        get_object_or_404(RoutineExercise, pk=re_pk, routine_day=day).delete()
    return redirect("training:routine-detail", pk=pk)


# --- Ejercicios ----------------------------------------------------------

@login_required
def exercise_list(request):
    exercises = Exercise.objects.filter(visible_exercises_q(request.user), is_active=True).select_related("primary_muscle")
    muscle = request.GET.get("muscle", "")
    if muscle:
        exercises = exercises.filter(primary_muscle__slug=muscle)
    query = request.GET.get("q", "").strip()
    if query:
        exercises = exercises.filter(name__icontains=query)
    from .models import MuscleGroup
    return render(request, "training/exercise_list.html", {
        "exercises": exercises, "muscle_groups": MuscleGroup.objects.all(),
        "selected_muscle": muscle, "query": query,
    })


@login_required
def exercise_detail(request, slug):
    exercise = get_object_or_404(Exercise.objects.filter(visible_exercises_q(request.user)), slug=slug)
    progression = strength_progression(request.user, exercise)
    prs = PersonalRecord.objects.filter(user=request.user, exercise=exercise)
    recent_sets = SetEntry.objects.filter(
        workout_exercise__exercise=exercise, workout_exercise__workout__user=request.user, completed=True,
    ).select_related("workout_exercise__workout").order_by("-workout_exercise__workout__date")[:20]
    chart_labels = [d.isoformat() for d, _ in progression]
    chart_values = [float(v) for _, v in progression]
    from .services import rep_max_table

    return render(request, "training/exercise_detail.html", {
        "exercise": exercise, "prs": prs, "recent_sets": recent_sets,
        "chart_labels": chart_labels, "chart_values": chart_values,
        "rep_max_table": rep_max_table(request.user, exercise),
    })


# --- Cuerpo ------------------------------------------------------------------

@login_required
def bodyweight(request):
    if request.method == "POST":
        form = BodyWeightEntryForm(request.POST)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.user = request.user
            entry.save()
            messages.success(request, "Peso registrado.")
            return redirect("training:bodyweight")
    else:
        last_entry = BodyWeightEntry.objects.filter(user=request.user).first()
        unit = last_entry.input_unit if last_entry else request.user.unit_preference
        form = BodyWeightEntryForm(initial={"date": timezone.localdate(), "unit": unit})
    entries = BodyWeightEntry.objects.filter(user=request.user)[:90]
    chart_labels = [e.date.isoformat() for e in reversed(entries)]
    chart_values = [float(e.weight_kg) for e in reversed(entries)]
    return render(request, "training/bodyweight.html", {
        "form": form, "entries": entries[:20],
        "chart_labels": chart_labels, "chart_values": chart_values,
    })


@login_required
def bodyweight_delete(request, pk):
    entry = get_object_or_404(BodyWeightEntry, pk=pk, user=request.user)
    if request.method == "POST":
        entry.delete()
    return redirect("training:bodyweight")


# --- Récords y objetivos ------------------------------------------------------

@login_required
def pr_list(request):
    records = PersonalRecord.objects.filter(user=request.user).select_related("exercise").order_by("exercise__name", "kind")
    return render(request, "training/pr_list.html", {"records": records})


@login_required
def analytics(request):
    from . import services

    user = request.user
    week = services.week_comparison(user)

    muscle_labels, muscle_series = services.muscle_volume_by_week(user, weeks=8)
    muscle_chart_series = [
        {"label": name, "values": [float(v) for v in values]}
        for name, values in muscle_series
    ]

    balance = services.muscle_balance(user, days=30)
    balance_total = sum((v for _, v in balance), Decimal("0"))
    balance_rows = [
        {"muscle": name, "volume": volume, "pct": round(float(volume) / float(balance_total) * 100) if balance_total else 0}
        for name, volume in balance
    ]

    rpe_labels, rpe_values = services.rpe_trend(user, weeks=8)

    heatmap_weeks = services.training_heatmap(user, weeks=16)
    top_lifts = services.top_lifts_progression(user, limit=4)
    top_lifts_chart = [
        {
            "label": lift["exercise"].name,
            "labels": [d.isoformat() for d, _ in lift["points"]],
            "values": [float(v) for _, v in lift["points"]],
        }
        for lift in top_lifts
    ]

    total_volume_labels, total_volume_values = services.total_volume_by_week(user, weeks=12)
    exercise_freq = services.exercise_frequency(user, weeks=8)

    context = {
        "total_volume_labels": total_volume_labels,
        "total_volume_values": [float(v) for v in total_volume_values],
        "has_total_volume_data": any(v > 0 for v in total_volume_values),
        "exercise_freq_labels": [name for name, _ in exercise_freq],
        "exercise_freq_values": [n for _, n in exercise_freq],
        "has_exercise_freq_data": bool(exercise_freq),
        "week": week,
        "muscle_chart_labels": muscle_labels,
        "muscle_chart_series": muscle_chart_series,
        "has_muscle_data": any(s["values"] for s in muscle_chart_series) and any(any(v > 0 for v in s["values"]) for s in muscle_chart_series),
        "balance_rows": balance_rows,
        "has_balance_data": bool(balance_rows),
        "rpe_labels": rpe_labels,
        # json.dumps, no la lista de Python tal cual -- rpe_values puede
        # traer None (semana sin RPE registrado) y el `None` de Python
        # se cuela literal en el <script> (no es `null` de JS), rompiendo
        # todo el bloque con un ReferenceError silencioso.
        "rpe_values_json": json.dumps(rpe_values),
        "has_rpe_data": any(v is not None for v in rpe_values),
        "heatmap_weeks": heatmap_weeks,
        "has_heatmap_data": any(day["volume"] for week_row in heatmap_weeks for day in week_row),
        "top_lifts_chart_json": json.dumps(top_lifts_chart),
        "has_top_lifts_data": bool(top_lifts_chart),
    }
    return render(request, "training/analytics.html", context)


@login_required
def competition(request):
    from . import services

    period = request.GET.get("period", "week")
    if period not in ("today", "week"):
        period = "week"

    scope = request.GET.get("scope", "all")
    if scope not in ("all", "friends"):
        scope = "all"

    points_rows = services.leaderboard_points(period)
    volume_rows = services.leaderboard_volume(period)
    workouts_rows = services.leaderboard_workouts(period)
    streak_rows = services.leaderboard_streaks()

    if scope == "friends":
        from accounts.models import friends_of

        allowed = {f.username for f in friends_of(request.user)} | {request.user.username}
        points_rows = [row for row in points_rows if row[0] in allowed]
        volume_rows = [row for row in volume_rows if row[0] in allowed]
        workouts_rows = [row for row in workouts_rows if row[0] in allowed]
        streak_rows = [row for row in streak_rows if row[0] in allowed]

    def with_rank_and_you(rows):
        return [
            {"rank": i + 1, "username": username, "value": value, "is_you": username == request.user.username}
            for i, (username, value) in enumerate(rows)
        ]

    return render(request, "training/competition.html", {
        "period": period,
        "scope": scope,
        "points_rows": with_rank_and_you(points_rows),
        "volume_rows": with_rank_and_you(volume_rows),
        "workouts_rows": with_rank_and_you(workouts_rows),
        "streak_rows": with_rank_and_you(streak_rows),
    })


@login_required
def head_to_head(request):
    from django.contrib.auth import get_user_model

    from . import services

    User = get_user_model()
    opponents = User.objects.exclude(pk=request.user.pk).order_by("username")

    opponent = None
    rows = []
    username = request.GET.get("vs")
    if username:
        opponent = opponents.filter(username=username).first()
        if opponent:
            rows = services.head_to_head_rows(request.user, opponent)

    ahead_count = sum(1 for row in rows if row["ahead"] == "me")
    behind_count = sum(1 for row in rows if row["ahead"] == "them")

    return render(request, "training/head_to_head.html", {
        "opponents": opponents,
        "opponent": opponent,
        "rows": rows,
        "ahead_count": ahead_count,
        "behind_count": behind_count,
    })


@login_required
def goal_list(request):
    from .services import goal_progress

    goals = Goal.objects.filter(user=request.user).select_related("exercise")
    rows = [{"goal": g, "progress": goal_progress(request.user, g)} for g in goals]
    return render(request, "training/goal_list.html", {"rows": rows})


@login_required
def goal_create(request):
    if request.method == "POST":
        form = GoalForm(request.POST, user=request.user)
        if form.is_valid():
            goal = form.save(commit=False)
            goal.user = request.user
            goal.save()
            return redirect("training:goal-list")
    else:
        form = GoalForm(user=request.user)
    return render(request, "training/goal_form.html", {
        "form": form, "exercises_json": json.dumps(exercises_picker_data(request.user)),
    })


@login_required
def goal_toggle(request, pk):
    goal = get_object_or_404(Goal, pk=pk, user=request.user)
    if request.method == "POST":
        goal.achieved = not goal.achieved
        goal.achieved_at = timezone.now() if goal.achieved else None
        goal.save(update_fields=["achieved", "achieved_at"])
    return redirect("training:goal-list")


@login_required
def goal_delete(request, pk):
    goal = get_object_or_404(Goal, pk=pk, user=request.user)
    if request.method == "POST":
        goal.delete()
    return redirect("training:goal-list")
