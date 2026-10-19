# usuarios/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .forms import UsuarioChangeForm, UsuarioCreationForm
from .models import PerfilSocio, Usuario


class PerfilSocioInline(admin.StackedInline):
    model = PerfilSocio
    can_delete = False


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    inlines = [PerfilSocioInline]
    add_form = UsuarioCreationForm
    form = UsuarioChangeForm
    model = Usuario
    ordering = ["email"]
    list_display = ["email", "nombre", "is_staff", "is_active"]
    search_fields = ["email", "nombre", "apellidos"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Datos personales", {"fields": ("nombre", "apellidos")}),
        (
            "Permisos",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Fechas", {"fields": ("last_login", "fecha_alta")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "nombre", "password1", "password2")}),
    )
