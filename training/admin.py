from django.contrib import admin

from .models import (
    BodyWeightEntry,
    Exercise,
    Goal,
    MuscleGroup,
    PersonalRecord,
    Routine,
    RoutineDay,
    RoutineExercise,
    SetEntry,
    Workout,
    WorkoutExercise,
)


@admin.register(MuscleGroup)
class MuscleGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "region")
    list_filter = ("region",)
    search_fields = ("name",)


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    list_display = ("name", "primary_muscle", "equipment", "category", "created_by", "is_active")
    list_filter = ("equipment", "category", "primary_muscle", "is_active")
    search_fields = ("name",)
    autocomplete_fields = ("primary_muscle", "secondary_muscles")


class RoutineExerciseInline(admin.TabularInline):
    model = RoutineExercise
    extra = 1
    autocomplete_fields = ("exercise",)


class RoutineDayInline(admin.StackedInline):
    model = RoutineDay
    extra = 1


@admin.register(Routine)
class RoutineAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "user__username")
    inlines = [RoutineDayInline]


@admin.register(RoutineDay)
class RoutineDayAdmin(admin.ModelAdmin):
    list_display = ("name", "routine", "order")
    inlines = [RoutineExerciseInline]


class SetEntryInline(admin.TabularInline):
    model = SetEntry
    extra = 1


class WorkoutExerciseInline(admin.TabularInline):
    model = WorkoutExercise
    extra = 1
    autocomplete_fields = ("exercise",)
    show_change_link = True


@admin.register(Workout)
class WorkoutAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "date", "status", "total_sets_display", "total_volume_display")
    list_filter = ("status", "date")
    search_fields = ("name", "user__username")
    inlines = [WorkoutExerciseInline]
    date_hierarchy = "date"

    @admin.display(description="Series")
    def total_sets_display(self, obj):
        return obj.total_sets

    @admin.display(description="Volumen (kg)")
    def total_volume_display(self, obj):
        return obj.total_volume_kg


@admin.register(WorkoutExercise)
class WorkoutExerciseAdmin(admin.ModelAdmin):
    list_display = ("workout", "exercise", "order", "superset_group")
    autocomplete_fields = ("exercise",)
    inlines = [SetEntryInline]


@admin.register(SetEntry)
class SetEntryAdmin(admin.ModelAdmin):
    list_display = ("workout_exercise", "set_number", "set_type", "weight_kg", "reps_performed", "rpe", "is_pr")
    list_filter = ("set_type", "is_pr", "completed")


@admin.register(PersonalRecord)
class PersonalRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "exercise", "kind", "value_kg", "reps", "achieved_at")
    list_filter = ("kind",)
    search_fields = ("user__username", "exercise__name")


@admin.register(BodyWeightEntry)
class BodyWeightEntryAdmin(admin.ModelAdmin):
    list_display = ("user", "date", "weight_kg", "body_fat_pct")
    list_filter = ("date",)
    search_fields = ("user__username",)
    date_hierarchy = "date"


@admin.register(Goal)
class GoalAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "kind", "target_date", "achieved")
    list_filter = ("kind", "achieved")
    search_fields = ("title", "user__username")
