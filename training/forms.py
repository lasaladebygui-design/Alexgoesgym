from django import forms
from django.db.models import Q

from .models import (
    BodyWeightEntry,
    Exercise,
    Goal,
    Routine,
    RoutineDay,
    RoutineExercise,
    SetEntry,
    Workout,
    WorkoutExercise,
)
from .utils import to_kg


class WorkoutStartForm(forms.Form):
    routine_day = forms.ModelChoiceField(
        label="Día de rutina", queryset=RoutineDay.objects.none(), required=False,
        help_text="Déjalo en blanco para un entrenamiento libre.",
    )
    name = forms.CharField(label="Nombre", max_length=150, required=False, help_text="Ej. «Pecho + tríceps». Se rellena solo si eliges un día.")

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["routine_day"].queryset = RoutineDay.objects.filter(
            routine__user=user, routine__is_active=True,
        ).select_related("routine")


class WorkoutFinishForm(forms.ModelForm):
    class Meta:
        model = Workout
        fields = ["energy_level", "rpe_session", "bodyweight_kg", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}


def visible_exercises_q(user):
    """Ejercicios visibles para `user`: los del catálogo global (sin
    dueño) más los que se haya creado él mismo."""
    return Q(created_by__isnull=True) | Q(created_by=user)


class WorkoutExerciseAddForm(forms.Form):
    exercise = forms.ModelChoiceField(label="Ejercicio", queryset=Exercise.objects.none(), empty_label="Elige un ejercicio...")
    superset_group = forms.IntegerField(label="Grupo de superserie", required=False, min_value=1)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["exercise"].queryset = Exercise.objects.filter(
            visible_exercises_q(user),
        ).select_related("primary_muscle").order_by("name")


class SetEntryForm(forms.ModelForm):
    weight = forms.DecimalField(label="Peso", max_digits=6, decimal_places=2, required=False)
    unit = forms.ChoiceField(label="Unidad", choices=[("kg", "kg"), ("lb", "lb")], initial="kg")

    class Meta:
        model = SetEntry
        fields = [
            "set_type", "custom_type_label", "reps_performed", "reps_target",
            "rpe", "rir", "percent_1rm", "tempo", "rest_seconds", "notes",
            "is_assisted", "completed",
        ]
        widgets = {
            "reps_performed": forms.NumberInput(attrs={"min": 0}),
            "reps_target": forms.NumberInput(attrs={"min": 0}),
            "rpe": forms.NumberInput(attrs={"step": "0.5", "min": 1, "max": 10}),
            "rir": forms.NumberInput(attrs={"min": 0, "max": 10}),
            "percent_1rm": forms.NumberInput(attrs={"step": "0.5", "min": 0, "max": 150}),
            "notes": forms.TextInput(),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        weight = self.cleaned_data.get("weight")
        unit = self.cleaned_data.get("unit") or "kg"
        instance.input_unit = unit
        instance.weight_kg = to_kg(weight, unit) if weight is not None else None
        if commit:
            instance.save()
        return instance


class BodyWeightEntryForm(forms.ModelForm):
    weight = forms.DecimalField(label="Peso", max_digits=5, decimal_places=2)
    unit = forms.ChoiceField(label="Unidad", choices=[("kg", "kg"), ("lb", "lb")], initial="kg")

    class Meta:
        model = BodyWeightEntry
        fields = ["date", "body_fat_pct", "notes"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}

    def save(self, commit=True):
        instance = super().save(commit=False)
        weight = self.cleaned_data["weight"]
        unit = self.cleaned_data["unit"]
        instance.input_unit = unit
        instance.weight_kg = to_kg(weight, unit)
        if commit:
            instance.save()
        return instance


class RoutineForm(forms.ModelForm):
    class Meta:
        model = Routine
        fields = ["name", "description", "is_active"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class RoutineDayForm(forms.ModelForm):
    class Meta:
        model = RoutineDay
        fields = ["name", "order"]


class RoutineExerciseForm(forms.ModelForm):
    class Meta:
        model = RoutineExercise
        fields = [
            "exercise", "order", "superset_group", "target_sets",
            "target_reps_min", "target_reps_max", "target_rpe", "rest_seconds", "notes",
        ]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["exercise"].queryset = Exercise.objects.filter(visible_exercises_q(user)).order_by("name")
        self.fields["exercise"].empty_label = "Elige un ejercicio..."


class GoalForm(forms.ModelForm):
    class Meta:
        model = Goal
        fields = [
            "kind", "title", "exercise", "target_value_kg", "target_reps",
            "target_workouts_per_week", "target_date", "notes",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
            "target_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["exercise"].queryset = Exercise.objects.filter(visible_exercises_q(user)).order_by("name")
        self.fields["exercise"].required = False
        self.fields["exercise"].empty_label = "Ninguno en particular"
