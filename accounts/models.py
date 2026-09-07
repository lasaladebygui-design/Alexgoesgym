from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q


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


class FriendRequest(models.Model):
    """Solicitud de amistad -- mientras `accepted=False` está pendiente;
    al aceptarla, la propia fila aceptada ES la amistad (sin un modelo
    Friendship aparte). Sirve para filtrar la Liga/Competición a "solo
    tus amigos" en vez del ranking global de todo el mundo con cuenta."""

    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_friend_requests",
    )
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="received_friend_requests",
    )
    accepted = models.BooleanField("aceptada", default=False)
    created_at = models.DateTimeField("creada", auto_now_add=True)

    class Meta:
        verbose_name = "solicitud de amistad"
        verbose_name_plural = "solicitudes de amistad"
        constraints = [
            models.UniqueConstraint(fields=["from_user", "to_user"], name="una_solicitud_por_par_tonnage"),
        ]

    def __str__(self):
        estado = "amigos" if self.accepted else "pendiente"
        return f"{self.from_user} → {self.to_user} ({estado})"


def are_friends(user_a, user_b):
    return FriendRequest.objects.filter(
        Q(from_user=user_a, to_user=user_b) | Q(from_user=user_b, to_user=user_a),
        accepted=True,
    ).exists()


def friends_of(user):
    accepted = FriendRequest.objects.filter(
        Q(from_user=user, accepted=True) | Q(to_user=user, accepted=True)
    ).select_related("from_user", "to_user")
    return [fr.to_user if fr.from_user_id == user.pk else fr.from_user for fr in accepted]


def friendship_status(viewer, other):
    """'self' | 'friends' | 'pending_outgoing' | 'pending_incoming' | 'none'."""
    if viewer.pk == other.pk:
        return "self"
    if are_friends(viewer, other):
        return "friends"
    if FriendRequest.objects.filter(from_user=viewer, to_user=other, accepted=False).exists():
        return "pending_outgoing"
    if FriendRequest.objects.filter(from_user=other, to_user=viewer, accepted=False).exists():
        return "pending_incoming"
    return "none"
