from django.urls import path

from . import views

app_name = "training"

urlpatterns = [
    path("entrenar/nuevo/", views.workout_start, name="workout-start"),
    path("entrenar/<int:pk>/", views.workout_session, name="workout-session"),
    path("entrenar/<int:pk>/terminar/", views.workout_finish, name="workout-finish"),
    path("entrenar/<int:pk>/cancelar/", views.workout_cancel, name="workout-cancel"),
    path("entrenar/<int:pk>/ejercicio/anadir/", views.workout_exercise_add, name="workout-exercise-add"),
    path("entrenar/<int:pk>/ejercicio/<int:we_pk>/borrar/", views.workout_exercise_delete, name="workout-exercise-delete"),
    path("entrenar/<int:pk>/ejercicio/<int:we_pk>/serie/anadir/", views.set_add, name="set-add"),
    path("entrenar/<int:pk>/serie/<int:set_pk>/editar/", views.set_edit, name="set-edit"),
    path("entrenar/<int:pk>/serie/<int:set_pk>/borrar/", views.set_delete, name="set-delete"),

    path("entrenamientos/", views.workout_history, name="workout-history"),
    path("entrenamientos/<int:pk>/", views.workout_detail, name="workout-detail"),
    path("entrenamientos/<int:pk>/repetir/", views.workout_repeat, name="workout-repeat"),

    path("rutinas/", views.routine_list, name="routine-list"),
    path("rutinas/nueva/", views.routine_create, name="routine-create"),
    path("rutinas/<int:pk>/", views.routine_detail, name="routine-detail"),
    path("rutinas/<int:pk>/borrar/", views.routine_delete, name="routine-delete"),
    path("rutinas/<int:pk>/dia/anadir/", views.routine_day_add, name="routine-day-add"),
    path("rutinas/<int:pk>/dia/<int:day_pk>/borrar/", views.routine_day_delete, name="routine-day-delete"),
    path("rutinas/<int:pk>/dia/<int:day_pk>/ejercicio/anadir/", views.routine_exercise_add, name="routine-exercise-add"),
    path("rutinas/<int:pk>/dia/<int:day_pk>/ejercicio/<int:re_pk>/borrar/", views.routine_exercise_delete, name="routine-exercise-delete"),

    path("ejercicios/", views.exercise_list, name="exercise-list"),
    path("ejercicios/<slug:slug>/", views.exercise_detail, name="exercise-detail"),

    path("cuerpo/", views.bodyweight, name="bodyweight"),
    path("cuerpo/<int:pk>/borrar/", views.bodyweight_delete, name="bodyweight-delete"),

    path("records/", views.pr_list, name="pr-list"),
    path("analiticas/", views.analytics, name="analytics"),
    path("competicion/", views.competition, name="competition"),

    path("objetivos/", views.goal_list, name="goal-list"),
    path("objetivos/nuevo/", views.goal_create, name="goal-create"),
    path("objetivos/<int:pk>/toggle/", views.goal_toggle, name="goal-toggle"),
    path("objetivos/<int:pk>/borrar/", views.goal_delete, name="goal-delete"),
]
