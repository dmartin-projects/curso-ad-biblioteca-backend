# usuarios/models.py
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from .managers import UsuarioManager


class Usuario(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField("email", unique=True)
    nombre = models.CharField(max_length=150, blank=True)
    apellidos = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    fecha_alta = models.DateTimeField(default=timezone.now)

    objects = UsuarioManager()

    USERNAME_FIELD = "email"  # campo con el que se identifica
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["nombre"]  # los pide createsuperuser (además de email y password)

    class Meta:
        verbose_name = "usuario"

    def __str__(self):
        return self.email

    def get_full_name(self):
        return f"{self.nombre} {self.apellidos}".strip()

    def get_short_name(self):
        return self.nombre


class PerfilSocio(models.Model):
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="socio"
    )
    numero = models.CharField(max_length=20, unique=True)
    telefono = models.CharField(max_length=20, blank=True)
    max_prestamos = models.PositiveSmallIntegerField(default=3)

    class Meta:
        verbose_name = "perfil de socio"
        verbose_name_plural = "perfiles de socio"

    def __str__(self):
        return self.numero
