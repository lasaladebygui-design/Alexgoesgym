from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class ProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="lifter", password="pass12345")
        self.client.force_login(self.user)

    def test_cambiar_unidad_preferida(self):
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)

        self.client.post(reverse("accounts:profile"), {
            "unit_preference": "lb", "height_cm": "", "birth_date": "",
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.unit_preference, "lb")

    def test_perfil_requiere_login(self):
        self.client.logout()
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 302)


class SignupTests(TestCase):
    def test_registro_crea_usuario_y_entra(self):
        response = self.client.post(reverse("accounts:signup"), {
            "username": "nuevo", "password1": "unaContrasenaSegura123", "password2": "unaContrasenaSegura123",
        })
        self.assertEqual(User.objects.filter(username="nuevo").count(), 1)
        self.assertRedirects(response, reverse("dashboard:home"))
