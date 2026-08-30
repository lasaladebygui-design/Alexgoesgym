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
from .services import strength_progression


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
    return render(request, "training/workout_start.html", {"form": form})


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
        initial = {"set_type": SetEntry.SetType.WORKING}
        if last:
            initial.update({
                "weight": last.weight_display, "unit": last.input_unit, "set_type": last.set_type,
                "reps_target": last.reps_target, "rpe": last.rpe, "rir": last.rir,
            })
        rows.append({
            "we": we, "sets": sets,
            "add_form": SetEntryForm(initial=initial),
            "volume": we.total_volume_kg,
        })

    add_exercise_form = WorkoutExerciseAddForm(user=request.user)
    finish_form = WorkoutFinishForm(instance=workout)
    return render(request, "training/workout_session.html", {
        "workout": workout, "rows": rows,
        "add_exercise_form": add_exercise_form, "finish_form": finish_form,
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
        from decimal import Decimal
        form = SetEntryForm(request.POST, instance=set_entry, initial={
            "weight": set_entry.weight_display, "unit": set_entry.input_unit,
        })
        if form.is_valid():
            form.save()
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
    return render(request, "training/routine_detail.html", {"routine": routine, "day_form": day_form, "re_form": re_form})


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
    return render(request, "training/exercise_detail.html", {
        "exercise": exercise, "prs": prs, "recent_sets": recent_sets,
        "chart_labels": chart_labels, "chart_values": chart_values,
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
        form = BodyWeightEntryForm(initial={"date": timezone.localdate()})
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
def goal_list(request):
    goals = Goal.objects.filter(user=request.user).select_related("exercise")
    return render(request, "training/goal_list.html", {"goals": goals})


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
    return render(request, "training/goal_form.html", {"form": form})


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
