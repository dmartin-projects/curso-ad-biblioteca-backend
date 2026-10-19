"""Ejercicio del módulo 12."""

import re

import pytest
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from django.core import mail

from usuarios.models import PerfilSocio, Usuario

pytestmark = pytest.mark.django_db


def test_usuario_por_email_y_superusuario():
    u = Usuario.objects.create_user("Ana@Example.COM", password="clave-segura-123", nombre="Ana")
    assert u.email == "Ana@example.com"  # normalize_email baja a minúsculas solo el dominio
    assert u.check_password("clave-segura-123") and not u.is_staff
    admin = Usuario.objects.create_superuser("admin@example.com", "clave-segura-123")
    assert admin.is_staff and admin.is_superuser
    with pytest.raises(ValueError, match="obligatorio"):
        Usuario.objects.create_user("", password="x")


def test_admin_con_perfil_inline(client):
    admin = Usuario.objects.create_superuser("admin@example.com", "clave-segura-123")
    socio = Usuario.objects.create_user("ana@example.com", nombre="Ana")
    PerfilSocio.objects.update_or_create(usuario=socio, defaults={"numero": "S-000001"})
    client.force_login(admin)
    assert client.get("/admin/usuarios/usuario/").status_code == 200
    r = client.get(f"/admin/usuarios/usuario/{socio.pk}/change/")
    assert r.status_code == 200 and b"S-000001" in r.content  # el inline del perfil
    assert client.get("/admin/usuarios/usuario/add/").status_code == 200


def test_entrar_actualiza_el_hash_a_argon2(client, settings):
    settings.PASSWORD_HASHERS = [
        "django.contrib.auth.hashers.Argon2PasswordHasher",
        "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    ]
    u = Usuario.objects.create_user("ana@example.com")
    u.password = make_password("clave-segura-123", hasher="pbkdf2_sha256")  # un usuario "antiguo"
    u.save()
    assert u.password.startswith("pbkdf2_sha256$")
    assert client.login(username="ana@example.com", password="clave-segura-123")
    u.refresh_from_db()
    assert u.password.startswith("argon2$")  # actualizado al entrar


def test_backend_email_o_numero_de_socio():
    u = Usuario.objects.create_user("ana@example.com", password="clave-segura-123")
    PerfilSocio.objects.update_or_create(usuario=u, defaults={"numero": "S-000001"})
    assert authenticate(username="ANA@example.com", password="clave-segura-123") == u  # iexact
    assert authenticate(username="S-000001", password="clave-segura-123") == u
    assert authenticate(username="S-000001", password="mala") is None
    assert authenticate(username="nadie@example.com", password="x") is None
    u.is_active = False
    u.save()
    assert authenticate(username="ana@example.com", password="clave-segura-123") is None


def test_flujo_de_reseteo_de_contrasena(client):
    Usuario.objects.create_user("ana@example.com", password="vieja-clave-123")
    r = client.post("/cuentas/password_reset/", {"email": "ana@example.com"})
    assert r.status_code == 302 and r["Location"] == "/cuentas/password_reset/done/"
    # un email que no existe recibe exactamente la misma respuesta (y no se envía nada)
    r2 = client.post("/cuentas/password_reset/", {"email": "nadie@example.com"})
    assert r2.status_code == 302 and len(mail.outbox) == 1

    enlace = re.search(r"/cuentas/reset/[^/]+/[^/\s]+/", mail.outbox[0].body).group()
    r = client.get(enlace)  # Django guarda el token en la sesión y redirige a .../set-password/
    assert r.status_code == 302
    r = client.post(
        r["Location"], {"new_password1": "nueva-clave-456", "new_password2": "nueva-clave-456"}
    )
    assert r.status_code == 302 and r["Location"] == "/cuentas/reset/done/"
    assert client.login(username="ana@example.com", password="nueva-clave-456")
    assert client.get(enlace).status_code == 200  # el enlace ya no vale: "enlace no válido"
