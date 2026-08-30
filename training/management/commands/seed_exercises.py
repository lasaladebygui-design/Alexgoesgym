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
    # --- Pecho -----------------------------------------------------------
    ("Press banca", "Pecho", ["Tríceps", "Hombros"], "barbell", "compound", False),
    ("Press banca inclinado", "Pecho", ["Tríceps", "Hombros"], "barbell", "compound", False),
    ("Press banca declinado", "Pecho", ["Tríceps"], "barbell", "compound", False),
    ("Press banca agarre cerrado", "Tríceps", ["Pecho", "Hombros"], "barbell", "compound", False),
    ("Press banca con mancuernas", "Pecho", ["Tríceps", "Hombros"], "dumbbell", "compound", False),
    ("Press inclinado con mancuernas", "Pecho", ["Tríceps", "Hombros"], "dumbbell", "compound", False),
    ("Press declinado con mancuernas", "Pecho", ["Tríceps"], "dumbbell", "compound", False),
    ("Press de pecho en máquina", "Pecho", ["Tríceps"], "machine", "compound", False),
    ("Aperturas con mancuerna", "Pecho", [], "dumbbell", "isolation", False),
    ("Aperturas inclinadas con mancuerna", "Pecho", [], "dumbbell", "isolation", False),
    ("Cruce de poleas", "Pecho", [], "cable", "isolation", False),
    ("Contractor (pec deck)", "Pecho", [], "machine", "isolation", False),
    ("Fondos en paralelas (pecho)", "Pecho", ["Tríceps", "Hombros"], "bodyweight", "compound", False),
    ("Flexiones", "Pecho", ["Tríceps", "Hombros"], "bodyweight", "compound", False),
    ("Flexiones con lastre", "Pecho", ["Tríceps", "Hombros"], "bodyweight", "compound", False),
    ("Pull-over con mancuerna", "Pecho", ["Espalda"], "dumbbell", "isolation", False),

    # --- Espalda -----------------------------------------------------------
    ("Dominadas", "Espalda", ["Bíceps"], "bodyweight", "compound", False),
    ("Dominadas supinas", "Espalda", ["Bíceps"], "bodyweight", "compound", False),
    ("Dominadas lastradas", "Espalda", ["Bíceps"], "bodyweight", "compound", False),
    ("Dominadas asistidas", "Espalda", ["Bíceps"], "machine", "compound", False),
    ("Jalón al pecho", "Espalda", ["Bíceps"], "cable", "compound", False),
    ("Jalón tras nuca", "Espalda", ["Bíceps"], "cable", "compound", False),
    ("Jalón con agarre cerrado", "Espalda", ["Bíceps"], "cable", "compound", False),
    ("Remo con barra", "Espalda", ["Bíceps"], "barbell", "compound", False),
    ("Remo Pendlay", "Espalda", ["Bíceps"], "barbell", "compound", False),
    ("Remo con mancuerna a un brazo", "Espalda", ["Bíceps"], "dumbbell", "compound", True),
    ("Remo en máquina", "Espalda", ["Bíceps"], "machine", "compound", False),
    ("Remo en punta (T-bar)", "Espalda", ["Bíceps"], "barbell", "compound", False),
    ("Remo en polea baja", "Espalda", ["Bíceps"], "cable", "compound", False),
    ("Remo invertido", "Espalda", ["Bíceps"], "bodyweight", "compound", False),
    ("Peso muerto", "Espalda", ["Isquiotibiales", "Glúteos", "Lumbares"], "barbell", "compound", False),
    ("Peso muerto sumo", "Glúteos", ["Isquiotibiales", "Espalda"], "barbell", "compound", False),
    ("Peso muerto con trap bar", "Espalda", ["Isquiotibiales", "Glúteos"], "barbell", "compound", False),
    ("Peso muerto a una pierna", "Isquiotibiales", ["Glúteos", "Espalda"], "dumbbell", "compound", True),
    ("Buenos días (good morning)", "Isquiotibiales", ["Espalda", "Glúteos"], "barbell", "compound", False),
    ("Hiperextensiones", "Lumbares", ["Glúteos", "Isquiotibiales"], "bodyweight", "isolation", False),
    ("Face pull", "Hombros", ["Espalda"], "cable", "isolation", False),
    ("Encogimientos con barra", "Espalda", [], "barbell", "isolation", False),
    ("Encogimientos con mancuernas", "Espalda", [], "dumbbell", "isolation", False),
    ("Pull-over en polea", "Espalda", ["Pecho"], "cable", "isolation", False),

    # --- Hombros -----------------------------------------------------------
    ("Press militar", "Hombros", ["Tríceps"], "barbell", "compound", False),
    ("Press militar con mancuernas", "Hombros", ["Tríceps"], "dumbbell", "compound", False),
    ("Press Arnold", "Hombros", ["Tríceps"], "dumbbell", "compound", False),
    ("Press tras nuca", "Hombros", ["Tríceps"], "barbell", "compound", False),
    ("Press de hombro en máquina", "Hombros", ["Tríceps"], "machine", "compound", False),
    ("Elevaciones laterales", "Hombros", [], "dumbbell", "isolation", False),
    ("Elevaciones laterales en polea", "Hombros", [], "cable", "isolation", True),
    ("Elevaciones frontales", "Hombros", [], "dumbbell", "isolation", False),
    ("Pájaros (elevación posterior)", "Hombros", ["Espalda"], "dumbbell", "isolation", False),
    ("Pájaros en polea", "Hombros", ["Espalda"], "cable", "isolation", False),
    ("Remo al mentón", "Hombros", ["Espalda"], "barbell", "isolation", False),

    # --- Bíceps -----------------------------------------------------------
    ("Curl de bíceps con barra", "Bíceps", [], "barbell", "isolation", False),
    ("Curl de bíceps con barra Z", "Bíceps", [], "barbell", "isolation", False),
    ("Curl de bíceps con mancuerna", "Bíceps", [], "dumbbell", "isolation", False),
    ("Curl martillo", "Bíceps", ["Antebrazo"], "dumbbell", "isolation", False),
    ("Curl concentrado", "Bíceps", [], "dumbbell", "isolation", True),
    ("Curl en banco Scott", "Bíceps", [], "barbell", "isolation", False),
    ("Curl en polea", "Bíceps", [], "cable", "isolation", False),
    ("Curl 21s", "Bíceps", [], "barbell", "isolation", False),
    ("Curl inverso", "Bíceps", ["Antebrazo"], "barbell", "isolation", False),

    # --- Tríceps -----------------------------------------------------------
    ("Press francés", "Tríceps", [], "barbell", "isolation", False),
    ("Press francés con mancuerna", "Tríceps", [], "dumbbell", "isolation", False),
    ("Extensión de tríceps en polea (cuerda)", "Tríceps", [], "cable", "isolation", False),
    ("Extensión de tríceps en polea (barra)", "Tríceps", [], "cable", "isolation", False),
    ("Patada de tríceps", "Tríceps", [], "dumbbell", "isolation", True),
    ("Fondos de tríceps en banco", "Tríceps", [], "bodyweight", "isolation", False),
    ("Extensión de tríceps sobre la cabeza", "Tríceps", [], "dumbbell", "isolation", False),

    # --- Antebrazo -----------------------------------------------------------
    ("Curl de muñeca", "Antebrazo", [], "barbell", "isolation", False),
    ("Curl de muñeca inverso", "Antebrazo", [], "barbell", "isolation", False),
    ("Paseo del granjero", "Antebrazo", ["Espalda", "Abdomen"], "dumbbell", "compound", False),

    # --- Cuádriceps -----------------------------------------------------------
    ("Sentadilla", "Cuádriceps", ["Glúteos", "Isquiotibiales"], "barbell", "compound", False),
    ("Sentadilla frontal", "Cuádriceps", ["Glúteos"], "barbell", "compound", False),
    ("Sentadilla búlgara", "Cuádriceps", ["Glúteos"], "dumbbell", "compound", True),
    ("Sentadilla goblet", "Cuádriceps", ["Glúteos"], "dumbbell", "compound", False),
    ("Sentadilla hack", "Cuádriceps", ["Glúteos"], "machine", "compound", False),
    ("Prensa de piernas", "Cuádriceps", ["Glúteos"], "machine", "compound", False),
    ("Zancadas", "Cuádriceps", ["Glúteos"], "dumbbell", "compound", True),
    ("Zancadas caminando", "Cuádriceps", ["Glúteos"], "dumbbell", "compound", True),
    ("Extensión de cuádriceps", "Cuádriceps", [], "machine", "isolation", False),
    ("Subida al cajón (step-up)", "Cuádriceps", ["Glúteos"], "dumbbell", "compound", True),
    ("Sissy squat", "Cuádriceps", [], "bodyweight", "isolation", False),

    # --- Isquiotibiales -----------------------------------------------------------
    ("Peso muerto rumano", "Isquiotibiales", ["Glúteos", "Espalda"], "barbell", "compound", False),
    ("Curl femoral tumbado", "Isquiotibiales", [], "machine", "isolation", False),
    ("Curl femoral sentado", "Isquiotibiales", [], "machine", "isolation", False),
    ("Curl femoral de pie", "Isquiotibiales", [], "machine", "isolation", True),

    # --- Glúteos -----------------------------------------------------------
    ("Hip thrust", "Glúteos", ["Isquiotibiales"], "barbell", "compound", False),
    ("Puente de glúteo", "Glúteos", [], "bodyweight", "isolation", False),
    ("Patada de glúteo en polea", "Glúteos", [], "cable", "isolation", True),
    ("Abducción de cadera en máquina", "Glúteos", [], "machine", "isolation", False),

    # --- Gemelos -----------------------------------------------------------
    ("Elevación de talones de pie", "Gemelos", [], "machine", "isolation", False),
    ("Elevación de talones sentado", "Gemelos", [], "machine", "isolation", False),
    ("Elevación de talones en prensa", "Gemelos", [], "machine", "isolation", False),

    # --- Abdomen / Lumbares -----------------------------------------------------------
    ("Crunch abdominal", "Abdomen", [], "bodyweight", "isolation", False),
    ("Crunch en polea", "Abdomen", [], "cable", "isolation", False),
    ("Elevación de piernas colgado", "Abdomen", [], "bodyweight", "isolation", False),
    ("Elevación de piernas tumbado", "Abdomen", [], "bodyweight", "isolation", False),
    ("Rueda abdominal", "Abdomen", ["Lumbares"], "bodyweight", "isolation", False),
    ("Plancha", "Abdomen", ["Lumbares"], "bodyweight", "isolation", False),
    ("Plancha lateral", "Abdomen", ["Lumbares"], "bodyweight", "isolation", True),
    ("Giro ruso", "Abdomen", [], "dumbbell", "isolation", False),
    ("Escaladores (mountain climbers)", "Abdomen", [], "bodyweight", "isolation", False),
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
