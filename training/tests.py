import json
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

    def test_el_formulario_de_serie_respeta_la_unidad_preferida(self):
        self.user.unit_preference = "lb"
        self.user.save(update_fields=["unit_preference"])
        workout = Workout.objects.create(user=self.user, name="Test", start_time=Workout.start_time.field.default())
        WorkoutExercise.objects.create(workout=workout, exercise=self.bench)

        response = self.client.get(reverse("training:workout-session", args=[workout.pk]))
        self.assertEqual(response.context["rows"][0]["add_form"].initial["unit"], "lb")

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

    def test_repetir_entrenamiento_clona_los_ejercicios_sin_las_series(self):
        squat = Exercise.objects.create(name="Sentadilla", primary_muscle=self.chest, equipment="barbell")
        original = Workout.objects.create(
            user=self.user, name="Piernas", status=Workout.Status.COMPLETED,
            start_time=Workout.start_time.field.default(),
        )
        we1 = WorkoutExercise.objects.create(workout=original, exercise=squat, order=0)
        SetEntry.objects.create(workout_exercise=we1, set_number=1, weight_kg=Decimal("100"), reps_performed=5)
        WorkoutExercise.objects.create(workout=original, exercise=self.bench, order=1)

        response = self.client.post(reverse("training:workout-repeat", args=[original.pk]))
        new_workout = Workout.objects.exclude(pk=original.pk).get(name="Piernas")
        self.assertRedirects(response, reverse("training:workout-session", args=[new_workout.pk]))
        self.assertEqual(new_workout.status, Workout.Status.IN_PROGRESS)
        self.assertEqual(list(new_workout.exercises.order_by("order").values_list("exercise__name", flat=True)), ["Sentadilla", "Press banca"])
        self.assertEqual(SetEntry.objects.filter(workout_exercise__workout=new_workout).count(), 0)

    def test_repetir_ultima_serie_de_un_toque(self):
        """El botón "🔁 Repetir última" reenvía los mismos valores de la
        última serie sin pasar por el formulario -- clave para poder
        apuntar entre repeticiones sin escribir nada."""
        workout = Workout.objects.create(user=self.user, name="Test", start_time=Workout.start_time.field.default())
        we = WorkoutExercise.objects.create(workout=workout, exercise=self.bench)
        SetEntry.objects.create(
            workout_exercise=we, set_number=1, set_type=SetEntry.SetType.WORKING,
            weight_kg=Decimal("80"), input_unit="kg", reps_performed=10, reps_target=10,
            rpe=Decimal("8"), rir=2, completed=True,
        )
        response = self.client.get(reverse("training:workout-session", args=[workout.pk]))
        self.assertContains(response, "Repetir última")

        self.client.post(reverse("training:set-add", args=[workout.pk, we.pk]), {
            "set_type": SetEntry.SetType.WORKING, "weight": "80", "unit": "kg",
            "reps_performed": "10", "reps_target": "10", "rpe": "8", "rir": "2", "completed": "on",
        })
        self.assertEqual(we.sets.count(), 2)
        second = we.sets.get(set_number=2)
        self.assertEqual(second.weight_kg, Decimal("80"))
        self.assertEqual(second.reps_performed, 10)

    def test_chips_de_ejercicios_recientes_en_la_sesion(self):
        """El ejercicio ya usado aparece como chip de un toque, sin
        necesidad de escribir para volver a elegirlo."""
        workout = Workout.objects.create(user=self.user, name="Test", start_time=Workout.start_time.field.default())
        WorkoutExercise.objects.create(workout=workout, exercise=self.bench)
        response = self.client.get(reverse("training:workout-session", args=[workout.pk]))
        self.assertContains(response, "Press banca")  # como chip reciente y como fila ya añadida

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

    def test_progreso_de_objetivo_de_pr_segun_el_1rm_actual(self):
        workout = Workout.objects.create(
            user=self.user, name="Test", status=Workout.Status.COMPLETED,
            start_time=Workout.start_time.field.default(),
        )
        we = WorkoutExercise.objects.create(workout=workout, exercise=self.bench)
        # 80kg x 5 -> 1RM estimado ~93,3kg (Epley).
        SetEntry.objects.create(workout_exercise=we, set_number=1, weight_kg=Decimal("80"), reps_performed=5)

        goal = Goal.objects.create(
            user=self.user, kind=Goal.Kind.EXERCISE_PR, title="100kg en banca",
            exercise=self.bench, target_value_kg=Decimal("100"),
        )
        from training.services import goal_progress
        progress = goal_progress(self.user, goal)
        self.assertIsNotNone(progress)
        self.assertAlmostEqual(float(progress["current"]), 93.33, places=1)
        self.assertEqual(progress["pct"], 93)

        response = self.client.get(reverse("training:goal-list"))
        self.assertContains(response, "93% del objetivo")


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

    def test_dashboard_muestra_grafica_de_volumen_semanal(self):
        workout = Workout.objects.create(
            user=self.user, name="Pecho", status=Workout.Status.COMPLETED,
            start_time=Workout.start_time.field.default(),
        )
        we = WorkoutExercise.objects.create(workout=workout, exercise=self.bench)
        SetEntry.objects.create(workout_exercise=we, set_number=1, weight_kg=Decimal("80"), reps_performed=10)

        response = self.client.get(reverse("dashboard:home"))
        self.assertContains(response, "volume-chart")
        self.assertContains(response, "Volumen semanal")
        # 12 semanas, la última con 800 kg (80kg x 10 reps) de volumen.
        self.assertEqual(len(response.context["volume_chart_values"]), 12)
        self.assertEqual(response.context["volume_chart_values"][-1], 800.0)


class AnalyticsTests(TonnageTestCase):
    """training:analytics -- comparación semanal, volumen por músculo,
    reparto y tendencia de RPE (ver training/services.py)."""

    def _completed_workout(self, days_ago=0):
        from datetime import timedelta

        from django.utils import timezone as tz

        return Workout.objects.create(
            user=self.user, name="Test", date=tz.localdate() - timedelta(days=days_ago),
            start_time=Workout.start_time.field.default(), status=Workout.Status.COMPLETED,
        )

    def test_pagina_carga_sin_datos(self):
        response = self.client.get(reverse("training:analytics"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Todavía no hay series registradas")

    def test_comparacion_semanal_detecta_subida_de_volumen(self):
        this_week = self._completed_workout(days_ago=0)
        we1 = WorkoutExercise.objects.create(workout=this_week, exercise=self.bench)
        SetEntry.objects.create(workout_exercise=we1, set_number=1, weight_kg=Decimal("100"), reps_performed=10)

        # Un desplazamiento fijo (antes: 8 días) cae dentro de "la semana
        # pasada" salvo justo los lunes, que es cuando este test se
        # ejecutó por primera vez en verde -- day_of_week + 3 siempre cae
        # a mitad de la semana pasada, pase lo que pase con qué día es hoy.
        from django.utils import timezone as tz
        days_ago = tz.localdate().weekday() + 3
        last_week = self._completed_workout(days_ago=days_ago)
        we2 = WorkoutExercise.objects.create(workout=last_week, exercise=self.bench)
        SetEntry.objects.create(workout_exercise=we2, set_number=1, weight_kg=Decimal("50"), reps_performed=10)

        response = self.client.get(reverse("training:analytics"))
        week = response.context["week"]
        self.assertEqual(week["this"]["volume"], Decimal("1000"))
        self.assertEqual(week["last"]["volume"], Decimal("500"))
        self.assertEqual(week["volume_delta"], 100)

    def test_sin_semana_pasada_el_delta_es_none_no_infinito(self):
        workout = self._completed_workout(days_ago=0)
        we = WorkoutExercise.objects.create(workout=workout, exercise=self.bench)
        SetEntry.objects.create(workout_exercise=we, set_number=1, weight_kg=Decimal("100"), reps_performed=10)

        response = self.client.get(reverse("training:analytics"))
        self.assertIsNone(response.context["week"]["volume_delta"])

    def test_volumen_por_musculo_agrupa_por_grupo(self):
        legs = MuscleGroup.objects.create(name="Piernas", region="lower")
        squat = Exercise.objects.create(name="Sentadilla", primary_muscle=legs, equipment="barbell")

        workout = self._completed_workout()
        we_chest = WorkoutExercise.objects.create(workout=workout, exercise=self.bench)
        SetEntry.objects.create(workout_exercise=we_chest, set_number=1, weight_kg=Decimal("80"), reps_performed=10)
        we_legs = WorkoutExercise.objects.create(workout=workout, exercise=squat)
        SetEntry.objects.create(workout_exercise=we_legs, set_number=1, weight_kg=Decimal("120"), reps_performed=5)

        response = self.client.get(reverse("training:analytics"))
        labels = [s["label"] for s in response.context["muscle_chart_series"]]
        self.assertIn("Pecho", labels)
        self.assertIn("Piernas", labels)

    def test_reparto_sobre_30_dias_suma_100_por_ciento(self):
        from .services import muscle_balance

        legs = MuscleGroup.objects.create(name="Piernas", region="lower")
        squat = Exercise.objects.create(name="Sentadilla", primary_muscle=legs, equipment="barbell")
        workout = self._completed_workout()
        we_chest = WorkoutExercise.objects.create(workout=workout, exercise=self.bench)
        SetEntry.objects.create(workout_exercise=we_chest, set_number=1, weight_kg=Decimal("100"), reps_performed=10)
        we_legs = WorkoutExercise.objects.create(workout=workout, exercise=squat)
        SetEntry.objects.create(workout_exercise=we_legs, set_number=1, weight_kg=Decimal("100"), reps_performed=10)

        response = self.client.get(reverse("training:analytics"))
        total_pct = sum(row["pct"] for row in response.context["balance_rows"])
        self.assertEqual(total_pct, 100)
        self.assertEqual(len(muscle_balance(self.user)), 2)

    def test_rpe_solo_cuenta_series_con_rpe(self):
        workout = self._completed_workout()
        we = WorkoutExercise.objects.create(workout=workout, exercise=self.bench)
        SetEntry.objects.create(workout_exercise=we, set_number=1, weight_kg=Decimal("80"), reps_performed=8, rpe=Decimal("8.5"))
        SetEntry.objects.create(workout_exercise=we, set_number=2, weight_kg=Decimal("80"), reps_performed=8)

        response = self.client.get(reverse("training:analytics"))
        self.assertTrue(response.context["has_rpe_data"])
        rpe_values = json.loads(response.context["rpe_values_json"])
        self.assertIn(8.5, rpe_values)

    def test_semanas_sin_rpe_se_serializan_como_null_no_como_none_de_python(self):
        # Bug real: pasar la lista de Python tal cual con |safe metía la
        # palabra "None" literal en el <script> (no es "null" de JS) y
        # rompía el bloque entero con un ReferenceError silencioso.
        workout = self._completed_workout(days_ago=0)
        we = WorkoutExercise.objects.create(workout=workout, exercise=self.bench)
        SetEntry.objects.create(workout_exercise=we, set_number=1, weight_kg=Decimal("80"), reps_performed=8, rpe=Decimal("8.0"))

        older_workout = self._completed_workout(days_ago=21)
        we2 = WorkoutExercise.objects.create(workout=older_workout, exercise=self.bench)
        SetEntry.objects.create(workout_exercise=we2, set_number=1, weight_kg=Decimal("80"), reps_performed=8, rpe=Decimal("7.0"))

        response = self.client.get(reverse("training:analytics"))
        self.assertIn("null", response.context["rpe_values_json"])
        self.assertNotIn("None", response.content.decode())

    def test_pagina_requiere_login(self):
        self.client.logout()
        response = self.client.get(reverse("training:analytics"))
        self.assertNotEqual(response.status_code, 200)


class RepMaxTableTests(TonnageTestCase):
    """training/services.py::rep_max_table -- a partir del 1RM estimado
    (PersonalRecord), fórmula de Epley invertida por número de reps."""

    def test_sin_pr_todavia_no_hay_tabla(self):
        response = self.client.get(reverse("training:exercise-detail", args=[self.bench.slug]))
        self.assertNotContains(response, "Tabla de repeticiones")

    def test_con_pr_la_tabla_sale_y_1rm_coincide(self):
        workout = Workout.objects.create(user=self.user, name="Test", start_time=Workout.start_time.field.default())
        we = WorkoutExercise.objects.create(workout=workout, exercise=self.bench)
        SetEntry.objects.create(workout_exercise=we, set_number=1, weight_kg=Decimal("100"), reps_performed=1)

        response = self.client.get(reverse("training:exercise-detail", args=[self.bench.slug]))
        self.assertContains(response, "Tabla de repeticiones")
        table = dict(response.context["rep_max_table"])
        self.assertEqual(table[1], Decimal("100.0"))
        self.assertLess(table[10], table[1])


class CompetitionTests(TonnageTestCase):
    """training:competition -- ranking entre todo el mundo con cuenta
    (sin sistema de amigos aparte, ver training/services.py)."""

    def _completed_workout(self, user, days_ago=0):
        from datetime import timedelta

        from django.utils import timezone as tz

        return Workout.objects.create(
            user=user, name="Test", date=tz.localdate() - timedelta(days=days_ago),
            start_time=Workout.start_time.field.default(), status=Workout.Status.COMPLETED,
        )

    def test_pagina_carga_sin_datos(self):
        response = self.client.get(reverse("training:competition"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nadie ha registrado series")

    def test_te_marca_a_ti_y_ordena_por_volumen(self):
        other = User.objects.create_user(username="rival", password="pass12345")

        workout = self._completed_workout(self.user)
        we = WorkoutExercise.objects.create(workout=workout, exercise=self.bench)
        SetEntry.objects.create(workout_exercise=we, set_number=1, weight_kg=Decimal("50"), reps_performed=10)

        other_workout = self._completed_workout(other)
        we2 = WorkoutExercise.objects.create(workout=other_workout, exercise=self.bench)
        SetEntry.objects.create(workout_exercise=we2, set_number=1, weight_kg=Decimal("100"), reps_performed=10)

        response = self.client.get(reverse("training:competition"))
        rows = response.context["volume_rows"]
        self.assertEqual(rows[0]["username"], "rival")
        self.assertEqual(rows[1]["username"], "lifter")
        self.assertTrue(rows[1]["is_you"])
        self.assertFalse(rows[0]["is_you"])

    def test_entrenamientos_de_la_semana_pasada_no_cuentan(self):
        self._completed_workout(self.user, days_ago=10)
        response = self.client.get(reverse("training:competition"))
        self.assertEqual(response.context["workouts_rows"], [])

    def test_pagina_requiere_login(self):
        self.client.logout()
        response = self.client.get(reverse("training:competition"))
        self.assertNotEqual(response.status_code, 200)
