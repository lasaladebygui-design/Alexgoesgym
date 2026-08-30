from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User


class SignupForm(UserCreationForm):
    class Meta:
        model = User
        fields = ["username", "email"]


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["unit_preference", "height_cm", "birth_date", "avatar"]
        widgets = {"birth_date": forms.DateInput(attrs={"type": "date"})}
