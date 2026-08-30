from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import (
    BodyWeightEntry,
    Exercise,
    Goal,
    MuscleGroup,
    PersonalRecord,
    Routine,
    RoutineDay,
    SetEntry,
    Workout,
    WorkoutExercise,
)

User = get_user_model()


class TonnageTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="lifter", password="pass12345")
        self.client.force_login(self.user)
        self.chest = MuscleGroup.objects.create(name="Pecho", region="upper")
        self.bench = Exercise.objects.create(name="Press banca", primary_muscle=self.chest, equipment="barbell")


class WorkoutFlowTests(TonnageTestCase):
    """La función principal: empezar un entrenamiento, añadir un
    ejercicio, registrar series con detalle y terminarlo."""

    def test_flujo_completo_de_entrenamiento(self):
        # 1) Empezar libre
        response = self.client.post(reverse("training:workout-start"), {"routine_day": "", "name": "Empuje"})
        workout = Workout.objects.get(user=self.user)
        self.assertRedirects(response, reverse("training:workout-session", args=[workout.pk]))
        self.assertEqual(workout.status, Workout.Status.IN_PROGRESS)

        # 2) Añadir un ejercicio
        self.client.post(reverse("training:workout-exercise-add", args=[workout.pk]), {
            "exercise": self.bench.pk, "superset_group": "",
        })
        we = WorkoutExercise.objects.get(workout=workout, exercise=self.bench)

        # 3) Registrar dos series con mucho detalle
        self.client.post(reverse("training:set-add", args=[workout.pk, we.pk]), {
            "set_type": SetEntry.SetType.WORKING, "weight": "80", "unit": "kg",
            "reps_performed": "10", "reps_target": "10", "rpe": "8", "rir": "2",
            "percent_1rm": "75", "tempo": "2-0-1-0", "rest_seconds": "120", "completed": "on",
        })
        self.client.post(reverse("training:set-add", args=[workout.pk, we.pk]), {
            "set_type": SetEntry.SetType.TOP_SET, "weight": "85", "unit": "kg",
            "reps_performed": "8", "reps_target": "8", "completed": "on",
        })
        self.assertEqual(we.sets.count(), 2)

        # La pantalla de sesión activa (con cronómetro, tabla de series y
        # formularios de añadir) renderiza sin errores con datos reales.
        response = self.client.get(reverse("training:workout-session", args=[workout.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Press banca")
        self.assertContains(response, "80")

        first_set = we.sets.get(set_number=1)
        self.assertEqual(first_set.weight_kg, Decimal("80"))
        self.assertIsNotNone(first_set.estimated_1rm_kg)

        # Un PR de peso máximo se detecta solo con la segunda serie (85 > 80)
        pr = PersonalRecord.objects.get(user=self.user, exercise=self.bench, kind=PersonalRecord.Kind.WEIGHT)
        self.assertEqual(pr.value_kg, Decimal("85"))
        self.assertTrue(we.sets.get(set_number=2).is_pr)

        # 4) Terminar el entrenamiento
        response = self.client.post(reverse("training:workout-finish", args=[workout.pk]), {
            "energy_level": 4, "rpe_session": "8", "notes": "Buena sesión",
        })
        workout.refresh_from_db()
        self.assertEqual(workout.status, Workout.Status.COMPLETED)
        self.assertIsNotNone(workout.end_time)
        self.assertRedirects(response, reverse("training:workout-detail", args=[workout.pk]))

        # 5) Ya no se puede volver a la pantalla de sesión activa
        response = self.client.get(reverse("training:workout-session", args=[workout.pk]))
        self.assertRedirects(response, reverse("training:workout-detail", args=[workout.pk]))

        # 6) Aparece en el historial
        response = self.client.get(reverse("training:workout-history"))
        self.assertContains(response, "Empuje")

        # 7) La ficha del entrenamiento y la del ejercicio (con su gráfica
        # de progresión y sus PRs) renderizan bien con datos reales.
        response = self.client.get(reverse("training:workout-detail", args=[workout.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Press banca")

        response = self.client.get(reverse("training:exercise-detail", args=[self.bench.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Peso máximo")

        response = self.client.get(reverse("training:pr-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Press banca")

    def test_editar_una_serie_ya_registrada(self):
        workout = Workout.objects.create(user=self.user, name="Test", start_time=Workout.start_time.field.default())
        we = WorkoutExercise.objects.create(workout=workout, exercise=self.bench)
        set_entry = SetEntry.objects.create(
            workout_exercise=we, set_number=1, weight_kg=Decimal("50"), reps_performed=10, completed=True,
        )
        response = self.client.post(reverse("training:set-edit", args=[workout.pk, set_entry.pk]), {
            "set_type": SetEntry.SetType.TOP_SET, "weight": "60", "unit": "kg",
            "reps_performed": "8", "completed": "on",
        })
        self.assertRedirects(response, reverse("training:workout-session", args=[workout.pk]))
        set_entry.refresh_from_db()
        self.assertEqual(set_entry.weight_kg, Decimal("60"))
        self.assertEqual(set_entry.reps_performed, 8)
        self.assertEqual(set_entry.set_type, SetEntry.SetType.TOP_SET)

        # La pantalla de sesión, con el formulario de edición ya montado
        # para cada serie, sigue renderizando bien.
        response = self.client.get(reverse("training:workout-session", args=[workout.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "60")

    def test_borrar_una_serie_renumera_las_siguientes(self):
        workout = Workout.objects.create(user=self.user, name="Test", start_time=Workout.start_time.field.default())
        we = WorkoutExercise.objects.create(workout=workout, exercise=self.bench)
        for i in range(3):
            SetEntry.objects.create(workout_exercise=we, set_number=i + 1, weight_kg=50, reps_performed=10)
        middle = we.sets.get(set_number=2)
        self.client.post(reverse("training:set-delete", args=[workout.pk, middle.pk]))
        self.assertEqual(list(we.sets.order_by("set_number").values_list("set_number", flat=True)), [1, 2])

    def test_no_se_puede_acceder_al_entrenamiento_de_otro_usuario(self):
        other = User.objects.create_user(username="otro", password="pass12345")
        workout = Workout.objects.create(user=other, name="Ajeno", start_time=Workout.start_time.field.default())
        response = self.client.get(reverse("training:workout-session", args=[workout.pk]))
        self.assertEqual(response.status_code, 404)

    def test_lista_de_ejercicios_y_filtro_por_musculo(self):
        response = self.client.get(reverse("training:exercise-list"))
        self.assertContains(response, "Press banca")

        response = self.client.get(reverse("training:exercise-list"), {"muscle": self.chest.slug})
        self.assertContains(response, "Press banca")

        response = self.client.get(reverse("training:exercise-list"), {"q": "sentadilla"})
        self.assertNotContains(response, "Press banca")


class RoutineTests(TonnageTestCase):
    def test_crear_rutina_con_dia_y_ejercicio(self):
        self.client.post(reverse("training:routine-create"), {"name": "PPL", "description": "", "is_active": "on"})
        routine = Routine.objects.get(user=self.user, name="PPL")

        self.client.post(reverse("training:routine-day-add", args=[routine.pk]), {"name": "Empuje", "order": 0})
        day = RoutineDay.objects.get(routine=routine)

        self.client.post(reverse("training:routine-exercise-add", args=[routine.pk, day.pk]), {
            "exercise": self.bench.pk, "order": 0, "target_sets": 4,
            "target_reps_min": 6, "target_reps_max": 10,
        })
        self.assertEqual(day.exercises.count(), 1)

        # Empezar un entrenamiento desde ese día precarga sus ejercicios
        response = self.client.post(reverse("training:workout-start"), {"routine_day": day.pk, "name": ""})
        workout = Workout.objects.get(routine_day=day)
        self.assertRedirects(response, reverse("training:workout-session", args=[workout.pk]))
        self.assertEqual(workout.name, "Empuje")
        self.assertEqual(workout.exercises.count(), 1)
        self.assertEqual(workout.exercises.first().exercise, self.bench)

        response = self.client.get(reverse("training:routine-detail", args=[routine.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Press banca")


class BodyWeightTests(TonnageTestCase):
    def test_registrar_peso_en_libras_se_guarda_en_kg(self):
        self.client.post(reverse("training:bodyweight"), {
            "date": "2026-01-15", "weight": "220", "unit": "lb", "body_fat_pct": "",
        })
        entry = BodyWeightEntry.objects.get(user=self.user)
        self.assertAlmostEqual(float(entry.weight_kg), 99.79, places=1)
        self.assertEqual(entry.input_unit, "lb")
        self.assertAlmostEqual(float(entry.weight_display), 220, places=0)

        response = self.client.get(reverse("training:bodyweight"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "220")


class GoalTests(TonnageTestCase):
    def test_crear_y_marcar_objetivo_conseguido(self):
        self.client.post(reverse("training:goal-create"), {
            "kind": Goal.Kind.EXERCISE_PR, "title": "100kg en banca", "exercise": self.bench.pk,
            "target_value_kg": "100",
        })
        goal = Goal.objects.get(user=self.user)
        self.assertFalse(goal.achieved)
        self.client.post(reverse("training:goal-toggle", args=[goal.pk]))
        goal.refresh_from_db()
        self.assertTrue(goal.achieved)

        response = self.client.get(reverse("training:goal-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "100kg en banca")


class DashboardTests(TonnageTestCase):
    def test_dashboard_carga_sin_datos(self):
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 200)

    def test_dashboard_con_datos(self):
        workout = Workout.objects.create(
            user=self.user, name="Pecho", status=Workout.Status.COMPLETED,
            start_time=Workout.start_time.field.default(),
        )
        we = WorkoutExercise.objects.create(workout=workout, exercise=self.bench)
        SetEntry.objects.create(workout_exercise=we, set_number=1, weight_kg=80, reps_performed=10)
        BodyWeightEntry.objects.create(user=self.user, weight_kg=80, input_unit="kg")

        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pecho")
