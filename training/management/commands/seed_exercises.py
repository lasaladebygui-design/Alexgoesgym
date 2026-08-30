from django.core.management.base import BaseCommand

from training.models import Exercise, MuscleGroup

MUSCLE_GROUPS = [
    ("Pecho", "upper"),
    ("Espalda", "upper"),
    ("Hombros", "upper"),
    ("Bíceps", "upper"),
    ("Tríceps", "upper"),
    ("Antebrazo", "upper"),
    ("Cuádriceps", "lower"),
    ("Isquiotibiales", "lower"),
    ("Glúteos", "lower"),
    ("Gemelos", "lower"),
    ("Abdomen", "core"),
    ("Lumbares", "core"),
]

# (nombre, músculo principal, [secundarios], equipo, categoría, unilateral)
EXERCISES = [
    ("Press banca", "Pecho", ["Tríceps", "Hombros"], "barbell", "compound", False),
    ("Press banca inclinado", "Pecho", ["Tríceps", "Hombros"], "barbell", "compound", False),
    ("Press banca con mancuernas", "Pecho", ["Tríceps", "Hombros"], "dumbbell", "compound", False),
    ("Aperturas con mancuerna", "Pecho", [], "dumbbell", "isolation", False),
    ("Fondos en paralelas", "Pecho", ["Tríceps", "Hombros"], "bodyweight", "compound", False),
    ("Press militar", "Hombros", ["Tríceps"], "barbell", "compound", False),
    ("Press Arnold", "Hombros", ["Tríceps"], "dumbbell", "compound", False),
    ("Elevaciones laterales", "Hombros", [], "dumbbell", "isolation", False),
    ("Elevaciones frontales", "Hombros", [], "dumbbell", "isolation", False),
    ("Pájaros (elevación posterior)", "Hombros", ["Espalda"], "dumbbell", "isolation", False),
    ("Dominadas", "Espalda", ["Bíceps"], "bodyweight", "compound", False),
    ("Jalón al pecho", "Espalda", ["Bíceps"], "cable", "compound", False),
    ("Remo con barra", "Espalda", ["Bíceps"], "barbell", "compound", False),
    ("Remo con mancuerna a un brazo", "Espalda", ["Bíceps"], "dumbbell", "compound", True),
    ("Remo en máquina", "Espalda", ["Bíceps"], "machine", "compound", False),
    ("Peso muerto", "Espalda", ["Isquiotibiales", "Glúteos", "Lumbares"], "barbell", "compound", False),
    ("Peso muerto rumano", "Isquiotibiales", ["Glúteos", "Espalda"], "barbell", "compound", False),
    ("Curl de bíceps con barra", "Bíceps", [], "barbell", "isolation", False),
    ("Curl de bíceps con mancuerna", "Bíceps", [], "dumbbell", "isolation", False),
    ("Curl martillo", "Bíceps", ["Antebrazo"], "dumbbell", "isolation", False),
    ("Press francés", "Tríceps", [], "barbell", "isolation", False),
    ("Extensión de tríceps en polea", "Tríceps", [], "cable", "isolation", False),
    ("Fondos de tríceps en banco", "Tríceps", [], "bodyweight", "isolation", False),
    ("Sentadilla", "Cuádriceps", ["Glúteos", "Isquiotibiales"], "barbell", "compound", False),
    ("Sentadilla frontal", "Cuádriceps", ["Glúteos"], "barbell", "compound", False),
    ("Prensa de piernas", "Cuádriceps", ["Glúteos"], "machine", "compound", False),
    ("Zancadas", "Cuádriceps", ["Glúteos"], "dumbbell", "compound", True),
    ("Extensión de cuádriceps", "Cuádriceps", [], "machine", "isolation", False),
    ("Curl femoral", "Isquiotibiales", [], "machine", "isolation", False),
    ("Hip thrust", "Glúteos", ["Isquiotibiales"], "barbell", "compound", False),
    ("Elevación de talones de pie", "Gemelos", [], "machine", "isolation", False),
    ("Crunch abdominal", "Abdomen", [], "bodyweight", "isolation", False),
    ("Elevación de piernas colgado", "Abdomen", [], "bodyweight", "isolation", False),
    ("Plancha", "Abdomen", ["Lumbares"], "bodyweight", "isolation", False),
]


class Command(BaseCommand):
    help = "Crea (si no existen) los grupos musculares y ejercicios de catálogo básicos."

    def handle(self, *args, **options):
        groups = {}
        created_groups = 0
        for name, region in MUSCLE_GROUPS:
            group, created = MuscleGroup.objects.get_or_create(name=name, defaults={"region": region})
            groups[name] = group
            created_groups += created

        created_exercises = 0
        for name, primary, secondary, equipment, category, unilateral in EXERCISES:
            _, created = Exercise.objects.get_or_create(
                name=name, created_by=None,
                defaults={
                    "primary_muscle": groups[primary],
                    "equipment": equipment, "category": category, "unilateral": unilateral,
                },
            )
            if created:
                exercise = Exercise.objects.get(name=name, created_by=None)
                exercise.secondary_muscles.set([groups[m] for m in secondary])
            created_exercises += created

        self.stdout.write(self.style.SUCCESS(
            f"Grupos musculares: {created_groups} nuevos ({len(MUSCLE_GROUPS)} en total). "
            f"Ejercicios: {created_exercises} nuevos ({len(EXERCISES)} en total)."
        ))
