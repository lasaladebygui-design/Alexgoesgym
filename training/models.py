from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from .utils import estimated_1rm, from_kg, to_kg

User = settings.AUTH_USER_MODEL


class WeightUnit(models.TextChoices):
    KG = "kg", "kg"
    LB = "lb", "lb"


# --- Catálogo (compartido por todos los usuarios, con hueco para
# ejercicios propios de cada uno) -------------------------------------------

class MuscleGroup(models.Model):
    class Region(models.TextChoices):
        UPPER = "upper", "Tren superior"
        LOWER = "lower", "Tren inferior"
        CORE = "core", "Core"

    name = models.CharField("nombre", max_length=40, unique=True)
    slug = models.SlugField("slug", max_length=50, unique=True, blank=True)
    region = models.CharField("región", max_length=10, choices=Region.choices)

    class Meta:
        verbose_name = "grupo muscular"
        verbose_name_plural = "grupos musculares"
        ordering = ["region", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Exercise(models.Model):
    class Equipment(models.TextChoices):
        BARBELL = "barbell", "Barra"
        DUMBBELL = "dumbbell", "Mancuerna"
        MACHINE = "machine", "Máquina"
        CABLE = "cable", "Polea"
        BODYWEIGHT = "bodyweight", "Peso corporal"
        KETTLEBELL = "kettlebell", "Kettlebell"
        BAND = "band", "Bandas"
        OTHER = "other", "Otro"

    class Category(models.TextChoices):
        COMPOUND = "compound", "Multiarticular"
        ISOLATION = "isolation", "Analítico"

    name = models.CharField("nombre", max_length=100)
    slug = models.SlugField("slug", max_length=120, blank=True)
    primary_muscle = models.ForeignKey(
        MuscleGroup, verbose_name="músculo principal",
        on_delete=models.PROTECT, related_name="primary_exercises",
    )
    secondary_muscles = models.ManyToManyField(
        MuscleGroup, verbose_name="músculos secundarios",
        blank=True, related_name="secondary_exercises",
    )
    equipment = models.CharField("equipo", max_length=12, choices=Equipment.choices)
    category = models.CharField("categoría", max_length=10, choices=Category.choices, default=Category.COMPOUND)
    unilateral = models.BooleanField("unilateral", default=False, help_text="Se entrena un lado a la vez (ej. zancadas, remo a un brazo).")
    instructions = models.TextField("instrucciones", blank=True)
    # NULL = ejercicio del catálogo global (visible para todos). Si tiene
    # dueño, solo ese usuario lo ve/usa -- así cada cual puede añadir
    # variantes propias sin ensuciar el catálogo de nadie más.
    created_by = models.ForeignKey(
        User, verbose_name="creado por (vacío = catálogo global)",
        on_delete=models.CASCADE, null=True, blank=True, related_name="custom_exercises",
    )
    is_active = models.BooleanField("activo", default=True, help_text="Desmarca para archivarlo sin perder el historial de series ya registradas.")

    class Meta:
        verbose_name = "ejercicio"
        verbose_name_plural = "ejercicios"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["name"], condition=models.Q(created_by__isnull=True), name="nombre_unico_catalogo_global"),
            models.UniqueConstraint(fields=["created_by", "name"], condition=models.Q(created_by__isnull=False), name="nombre_unico_por_usuario"),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


# --- Rutinas: la plantilla de lo que se PLANEA hacer -----------------------

class Routine(models.Model):
    user = models.ForeignKey(User, verbose_name="usuario", on_delete=models.CASCADE, related_name="routines")
    name = models.CharField("nombre", max_length=100)
    description = models.TextField("descripción", blank=True)
    is_active = models.BooleanField("activa", default=True)
    created_at = models.DateTimeField("creada", auto_now_add=True)
    updated_at = models.DateTimeField("actualizada", auto_now=True)

    class Meta:
        verbose_name = "rutina"
        verbose_name_plural = "rutinas"
        ordering = ["-is_active", "-updated_at"]

    def __str__(self):
        return self.name


class RoutineDay(models.Model):
    routine = models.ForeignKey(Routine, verbose_name="rutina", on_delete=models.CASCADE, related_name="days")
    name = models.CharField("nombre", max_length=100, help_text="Ej. «Día A · Empuje», «Piernas», «Full body».")
    order = models.PositiveSmallIntegerField("orden", default=0)

    class Meta:
        verbose_name = "día de rutina"
        verbose_name_plural = "días de rutina"
        ordering = ["routine", "order"]

    def __str__(self):
        return f"{self.routine.name} · {self.name}"


class RoutineExercise(models.Model):
    routine_day = models.ForeignKey(RoutineDay, verbose_name="día", on_delete=models.CASCADE, related_name="exercises")
    exercise = models.ForeignKey(Exercise, verbose_name="ejercicio", on_delete=models.PROTECT, related_name="+")
    order = models.PositiveSmallIntegerField("orden", default=0)
    # Mismo número en varios RoutineExercise seguidos = superserie/circuito.
    superset_group = models.PositiveSmallIntegerField("grupo de superserie", null=True, blank=True)
    target_sets = models.PositiveSmallIntegerField("series objetivo", default=3)
    target_reps_min = models.PositiveSmallIntegerField("reps objetivo (mín.)", null=True, blank=True)
    target_reps_max = models.PositiveSmallIntegerField("reps objetivo (máx.)", null=True, blank=True)
    target_rpe = models.DecimalField("RPE objetivo", max_digits=3, decimal_places=1, null=True, blank=True)
    rest_seconds = models.PositiveIntegerField("descanso (s)", null=True, blank=True)
    notes = models.CharField("notas", max_length=255, blank=True)

    class Meta:
        verbose_name = "ejercicio de rutina"
        verbose_name_plural = "ejercicios de rutina"
        ordering = ["routine_day", "order"]

    def __str__(self):
        return f"{self.routine_day} · {self.exercise.name}"


# --- Entrenamientos: lo que REALMENTE se hizo -------------------------------

class Workout(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "En curso"
        COMPLETED = "completed", "Completado"
        CANCELLED = "cancelled", "Cancelado"

    class Energy(models.IntegerChoices):
        EXHAUSTED = 1, "Agotado 😩"
        LOW = 2, "Bajo 😐"
        NORMAL = 3, "Normal 🙂"
        GOOD = 4, "Con ganas 💪"
        PEAK = 5, "A tope 🔥"

    user = models.ForeignKey(User, verbose_name="usuario", on_delete=models.CASCADE, related_name="workouts")
    routine = models.ForeignKey(Routine, verbose_name="rutina", on_delete=models.SET_NULL, null=True, blank=True, related_name="workouts")
    routine_day = models.ForeignKey(RoutineDay, verbose_name="día de rutina", on_delete=models.SET_NULL, null=True, blank=True, related_name="workouts")
    name = models.CharField("nombre", max_length=150, help_text="Ej. «Pecho + tríceps». Se rellena solo desde el día de rutina si se elige uno.")
    date = models.DateField("fecha", default=timezone.localdate)
    start_time = models.DateTimeField("hora de inicio", default=timezone.now)
    end_time = models.DateTimeField("hora de fin", null=True, blank=True)
    status = models.CharField("estado", max_length=12, choices=Status.choices, default=Status.IN_PROGRESS)
    energy_level = models.PositiveSmallIntegerField("estado de energía", choices=Energy.choices, null=True, blank=True)
    rpe_session = models.DecimalField("RPE general", max_digits=3, decimal_places=1, null=True, blank=True)
    bodyweight_kg = models.DecimalField("peso corporal ese día (kg)", max_digits=5, decimal_places=2, null=True, blank=True)
    notes = models.TextField("notas", blank=True)

    class Meta:
        verbose_name = "entrenamiento"
        verbose_name_plural = "entrenamientos"
        ordering = ["-start_time"]

    def __str__(self):
        return f"{self.name} · {self.date}"

    @property
    def duration_seconds(self):
        if not self.end_time:
            return None
        return int((self.end_time - self.start_time).total_seconds())

    @property
    def duration_minutes(self):
        return self.duration_seconds // 60 if self.duration_seconds is not None else None

    def finish(self, when=None):
        self.end_time = when or timezone.now()
        self.status = self.Status.COMPLETED
        self.save(update_fields=["end_time", "status"])

    @property
    def total_volume_kg(self):
        return sum((s.weight_kg or 0) * s.reps_performed for s in self.all_sets() if s.reps_performed)

    @property
    def total_sets(self):
        return SetEntry.objects.filter(workout_exercise__workout=self).count()

    def all_sets(self):
        return SetEntry.objects.filter(workout_exercise__workout=self).select_related("workout_exercise__exercise")


class WorkoutExercise(models.Model):
    workout = models.ForeignKey(Workout, verbose_name="entrenamiento", on_delete=models.CASCADE, related_name="exercises")
    exercise = models.ForeignKey(Exercise, verbose_name="ejercicio", on_delete=models.PROTECT, related_name="workout_appearances")
    order = models.PositiveSmallIntegerField("orden", default=0)
    superset_group = models.PositiveSmallIntegerField("grupo de superserie", null=True, blank=True)
    notes = models.CharField("notas", max_length=255, blank=True)

    class Meta:
        verbose_name = "ejercicio del entrenamiento"
        verbose_name_plural = "ejercicios del entrenamiento"
        ordering = ["workout", "order"]

    def __str__(self):
        return f"{self.workout} · {self.exercise.name}"

    @property
    def total_volume_kg(self):
        return sum((s.weight_kg or 0) * s.reps_performed for s in self.sets.all() if s.reps_performed)


class SetEntry(models.Model):
    """La unidad atómica de todo el tracker: una serie, con todo lo que
    se pueda querer saber de ella. El peso se guarda SIEMPRE en kg
    (`weight_kg`); `input_unit` solo recuerda en qué unidad se escribió
    para poder enseñarlo tal cual se introdujo -- comparar PRs/volumen
    entre series en kg y en lb así no necesita conversión al vuelo."""

    class SetType(models.TextChoices):
        WARMUP = "warmup", "🔵 Calentamiento"
        WORKING = "working", "🟢 Trabajo"
        APPROACH = "approach", "🟡 Aproximación"
        TOP_SET = "top_set", "🔴 Top set"
        BACKOFF = "backoff", "🟣 Back-off"
        DROP_SET = "drop_set", "⚫ Drop set"
        REST_PAUSE = "rest_pause", "🟠 Rest-pause"
        MYO_REPS = "myo_reps", "🔵 Myo-reps"
        FAILURE = "failure", "⚪ Fallo"
        CUSTOM = "custom", "Personalizada"

    workout_exercise = models.ForeignKey(WorkoutExercise, verbose_name="ejercicio del entrenamiento", on_delete=models.CASCADE, related_name="sets")
    set_number = models.PositiveSmallIntegerField("número de serie")
    set_type = models.CharField("tipo de serie", max_length=12, choices=SetType.choices, default=SetType.WORKING)
    custom_type_label = models.CharField("etiqueta personalizada", max_length=40, blank=True)

    weight_kg = models.DecimalField("peso (kg)", max_digits=6, decimal_places=2, null=True, blank=True)
    input_unit = models.CharField("unidad introducida", max_length=2, choices=WeightUnit.choices, default=WeightUnit.KG)
    is_assisted = models.BooleanField("asistido", default=False, help_text="Máquina de asistencia: el peso resta carga en vez de sumarla (dominadas/fondos asistidos).")

    reps_performed = models.PositiveSmallIntegerField("repeticiones realizadas", null=True, blank=True)
    reps_target = models.PositiveSmallIntegerField("repeticiones objetivo", null=True, blank=True)

    rpe = models.DecimalField("RPE", max_digits=3, decimal_places=1, null=True, blank=True)
    rir = models.PositiveSmallIntegerField("RIR", null=True, blank=True)
    percent_1rm = models.DecimalField("% 1RM", max_digits=5, decimal_places=2, null=True, blank=True)
    estimated_1rm_kg = models.DecimalField("1RM estimado (kg)", max_digits=6, decimal_places=2, null=True, blank=True, editable=False)

    tempo = models.CharField("tempo", max_length=20, blank=True, help_text="Excéntrica-pausa-concéntrica-pausa, ej. «3-1-2-0».")
    rest_seconds = models.PositiveIntegerField("descanso previo (s)", null=True, blank=True)
    notes = models.CharField("notas", max_length=255, blank=True)

    completed = models.BooleanField("completada", default=True)
    is_pr = models.BooleanField("es un PR", default=False, editable=False)
    created_at = models.DateTimeField("creada", auto_now_add=True)

    class Meta:
        verbose_name = "serie"
        verbose_name_plural = "series"
        ordering = ["workout_exercise", "set_number"]
        constraints = [
            models.UniqueConstraint(fields=["workout_exercise", "set_number"], name="numero_serie_unico_por_ejercicio"),
        ]

    def __str__(self):
        peso = self.weight_display if self.weight_kg is not None else "—"
        return f"Serie {self.set_number}: {peso}{self.input_unit} × {self.reps_performed or '—'}"

    @property
    def weight_display(self):
        return from_kg(self.weight_kg, self.input_unit)

    def save(self, *args, **kwargs):
        if self.weight_kg is not None and self.reps_performed:
            self.estimated_1rm_kg = estimated_1rm(self.weight_kg, self.reps_performed)
        else:
            self.estimated_1rm_kg = None
        super().save(*args, **kwargs)
        self._update_prs()

    def _update_prs(self):
        """Recalcula (si hace falta) los PRs de este ejercicio para este
        usuario a raíz de guardar esta serie -- ver PersonalRecord."""
        if not self.completed or self.weight_kg is None or not self.reps_performed:
            return
        from .prs import refresh_prs_for_set
        refresh_prs_for_set(self)


# --- Récords personales (siempre el MEJOR actual por tipo y ejercicio) -----

class PersonalRecord(models.Model):
    class Kind(models.TextChoices):
        WEIGHT = "weight", "Peso máximo"
        EST_1RM = "est_1rm", "1RM estimado"
        REPS = "reps", "Repeticiones máximas"
        VOLUME_SESSION = "volume_session", "Volumen en una sesión"

    user = models.ForeignKey(User, verbose_name="usuario", on_delete=models.CASCADE, related_name="personal_records")
    exercise = models.ForeignKey(Exercise, verbose_name="ejercicio", on_delete=models.CASCADE, related_name="personal_records")
    kind = models.CharField("tipo", max_length=15, choices=Kind.choices)
    value_kg = models.DecimalField("valor (kg)", max_digits=8, decimal_places=2, null=True, blank=True)
    reps = models.PositiveSmallIntegerField("repeticiones", null=True, blank=True)
    set_entry = models.ForeignKey(SetEntry, verbose_name="serie de origen", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    workout = models.ForeignKey(Workout, verbose_name="entrenamiento de origen", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    achieved_at = models.DateTimeField("conseguido")

    class Meta:
        verbose_name = "récord personal"
        verbose_name_plural = "récords personales"
        ordering = ["-achieved_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "exercise", "kind"], name="un_pr_actual_por_tipo_y_ejercicio"),
        ]

    def __str__(self):
        return f"{self.exercise.name} · {self.get_kind_display()}: {self.value_kg}kg"


# --- Cuerpo y objetivos -----------------------------------------------------

class BodyWeightEntry(models.Model):
    user = models.ForeignKey(User, verbose_name="usuario", on_delete=models.CASCADE, related_name="bodyweight_entries")
    date = models.DateField("fecha", default=timezone.localdate)
    weight_kg = models.DecimalField("peso (kg)", max_digits=5, decimal_places=2)
    input_unit = models.CharField("unidad introducida", max_length=2, choices=WeightUnit.choices, default=WeightUnit.KG)
    body_fat_pct = models.DecimalField("% grasa corporal", max_digits=4, decimal_places=1, null=True, blank=True)
    notes = models.CharField("notas", max_length=255, blank=True)
    created_at = models.DateTimeField("creado", auto_now_add=True)

    class Meta:
        verbose_name = "entrada de peso corporal"
        verbose_name_plural = "entradas de peso corporal"
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.date}: {self.weight_display}{self.input_unit}"

    @property
    def weight_display(self):
        return from_kg(self.weight_kg, self.input_unit)


class Goal(models.Model):
    class Kind(models.TextChoices):
        EXERCISE_PR = "exercise_pr", "PR de ejercicio"
        BODYWEIGHT = "bodyweight", "Peso corporal"
        FREQUENCY = "frequency", "Frecuencia semanal"
        CUSTOM = "custom", "Personalizado"

    user = models.ForeignKey(User, verbose_name="usuario", on_delete=models.CASCADE, related_name="goals")
    kind = models.CharField("tipo", max_length=12, choices=Kind.choices)
    title = models.CharField("título", max_length=150)
    exercise = models.ForeignKey(Exercise, verbose_name="ejercicio", on_delete=models.SET_NULL, null=True, blank=True, related_name="goals")
    target_value_kg = models.DecimalField("valor objetivo (kg)", max_digits=8, decimal_places=2, null=True, blank=True)
    target_reps = models.PositiveSmallIntegerField("repeticiones objetivo", null=True, blank=True)
    target_workouts_per_week = models.PositiveSmallIntegerField("entrenamientos/semana objetivo", null=True, blank=True)
    target_date = models.DateField("fecha objetivo", null=True, blank=True)
    notes = models.TextField("notas", blank=True)
    achieved = models.BooleanField("conseguido", default=False)
    achieved_at = models.DateTimeField("conseguido el", null=True, blank=True)
    created_at = models.DateTimeField("creado", auto_now_add=True)

    class Meta:
        verbose_name = "objetivo"
        verbose_name_plural = "objetivos"
        ordering = ["achieved", "target_date"]

    def __str__(self):
        return self.title
