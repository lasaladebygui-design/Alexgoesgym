"""Recálculo de récords personales al guardar una serie.

Cada (usuario, ejercicio, tipo de récord) guarda solo el MEJOR valor
actual -- no un histórico completo -- porque el histórico ya vive en
SetEntry/Workout sin duplicar nada; esto es solo una caché para no
tener que agregar todas las series cada vez que el dashboard quiere
enseñar "tus PRs recientes"."""
from django.db.models import F, Sum
from django.utils import timezone


def refresh_prs_for_set(set_entry):
    from .models import PersonalRecord, SetEntry

    workout = set_entry.workout_exercise.workout
    exercise = set_entry.workout_exercise.exercise
    user = workout.user
    now = timezone.now()

    became_pr = False
    became_pr |= _maybe_update(
        user, exercise, PersonalRecord.Kind.WEIGHT,
        value_kg=set_entry.weight_kg, reps=set_entry.reps_performed,
        set_entry=set_entry, workout=workout, when=now,
    )
    if set_entry.estimated_1rm_kg is not None:
        became_pr |= _maybe_update(
            user, exercise, PersonalRecord.Kind.EST_1RM,
            value_kg=set_entry.estimated_1rm_kg, reps=set_entry.reps_performed,
            set_entry=set_entry, workout=workout, when=now,
        )
    became_pr |= _maybe_update(
        user, exercise, PersonalRecord.Kind.REPS,
        value_kg=set_entry.weight_kg, reps=set_entry.reps_performed,
        set_entry=set_entry, workout=workout, when=now, compare_field="reps",
    )

    session_volume = SetEntry.objects.filter(
        workout_exercise__workout=workout, workout_exercise__exercise=exercise,
        completed=True, weight_kg__isnull=False, reps_performed__isnull=False,
    ).aggregate(total=Sum(F("weight_kg") * F("reps_performed")))["total"]
    if session_volume:
        became_pr |= _maybe_update(
            user, exercise, PersonalRecord.Kind.VOLUME_SESSION,
            value_kg=session_volume, reps=None,
            set_entry=None, workout=workout, when=now,
        )

    if became_pr:
        # Update directo por queryset (no .save() de la instancia) para no
        # volver a disparar SetEntry.save() -> _update_prs() en bucle.
        SetEntry.objects.filter(pk=set_entry.pk).update(is_pr=True)


def _maybe_update(user, exercise, kind, *, value_kg, reps, set_entry, workout, when, compare_field="value_kg"):
    from .models import PersonalRecord

    record, created = PersonalRecord.objects.get_or_create(
        user=user, exercise=exercise, kind=kind,
        defaults={
            "value_kg": value_kg, "reps": reps, "set_entry": set_entry,
            "workout": workout, "achieved_at": when,
        },
    )
    if created:
        return True

    current = record.reps if compare_field == "reps" else record.value_kg
    candidate = reps if compare_field == "reps" else value_kg
    if candidate is None or current is not None and candidate <= current:
        return False

    record.value_kg = value_kg
    record.reps = reps
    record.set_entry = set_entry
    record.workout = workout
    record.achieved_at = when
    record.save(update_fields=["value_kg", "reps", "set_entry", "workout", "achieved_at"])
    return True
