from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Tonnage", {"fields": ("unit_preference", "height_cm", "birth_date", "avatar")}),
    )
    list_display = ("username", "email", "unit_preference", "is_staff")
