from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Usuario de Tonnage. Se parte de un modelo propio desde el principio
    (en vez del User por defecto de Django) porque cambiarlo más adelante
    obliga a rehacer todas las migraciones -- más vale pagar ese coste una
    vez, aquí, que nunca."""

    class WeightUnit(models.TextChoices):
        KG = "kg", "Kilogramos"
        LB = "lb", "Libras"

    unit_preference = models.CharField(
        "unidad preferida", max_length=2, choices=WeightUnit.choices, default=WeightUnit.KG,
    )
    height_cm = models.PositiveSmallIntegerField("altura (cm)", null=True, blank=True)
    birth_date = models.DateField("fecha de nacimiento", null=True, blank=True)
    avatar = models.ImageField("avatar", upload_to="avatars/", null=True, blank=True)

    def __str__(self):
        return self.get_full_name() or self.username
