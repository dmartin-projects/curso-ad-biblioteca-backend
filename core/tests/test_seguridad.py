"""Ejercicio del módulo 29: CSRF, autorización (IDOR), CORS, CSP y check --deploy."""

import json
import os
import secrets
import subprocess
import sys
from datetime import timedelta

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from catalogo.models import Ejemplar, Libro
from prestamos.models import Prestamo
from usuarios.models import Usuario

pytestmark = pytest.mark.django_db


@pytest.fixture
def ana_y_luis():
    libro = Libro.objects.create(titulo="Dune", isbn="9788497593793")
    ana = Usuario.objects.create_user("ana@example.com")
    luis = Usuario.objects.create_user("luis@example.com")
    prestamo_luis = Prestamo.objects.create(
        ejemplar=Ejemplar.objects.create(libro=libro, codigo="D1"),
        socio=luis,
        fecha_limite=timezone.now() + timedelta(days=21),
    )
    return ana, prestamo_luis


# ── 5. IDOR: cambiar el id en la URL no da acceso ──
def test_un_socio_no_ve_el_prestamo_de_otro(client, ana_y_luis):
    ana, prestamo_luis = ana_y_luis
    client.force_login(ana)
    assert client.get(reverse("prestamos:detalle", args=[prestamo_luis.pk])).status_code == 404
    assert client.get(f"/notas/prestamos/prestamo/{prestamo_luis.pk}/").status_code == 404
    assert prestamo_luis.pk not in [p["id"] for p in client.get("/prestamos/").json()["results"]]

    client.force_login(prestamo_luis.socio)  # su dueño sí
    assert client.get(reverse("prestamos:detalle", args=[prestamo_luis.pk])).status_code == 200


# ── CSRF: las views que usan la sesión exigen el token ──
def test_notas_exigen_token_csrf(ana_y_luis):
    luis = ana_y_luis[1].socio
    navegador = Client(enforce_csrf_checks=True)  # el Client normal se salta el CSRF
    navegador.force_login(luis)
    url = f"/notas/prestamos/prestamo/{ana_y_luis[1].pk}/"
    datos = json.dumps({"texto": "Llega tarde"})

    assert navegador.post(url, datos, content_type="application/json").status_code == 403

    navegador.get("/admin/login/")  # cualquier página con formulario fija la cookie csrftoken
    token = navegador.cookies["csrftoken"].value
    r = navegador.post(url, datos, content_type="application/json", headers={"x-csrftoken": token})
    assert r.status_code == 201  # lo que hará Angular con withXsrfConfiguration (módulo 51)


def test_crear_libro_exige_permiso(client, ana_y_luis):
    datos = json.dumps({"titulo": "Hyperion", "isbn": "9788498003253"})
    url = reverse("catalogo:crear_libro")
    assert client.post(url, datos, content_type="application/json").status_code == 403
    client.force_login(ana_y_luis[0])  # un socio tampoco: hace falta catalogo.add_libro
    assert client.post(url, datos, content_type="application/json").status_code == 403


# ── 2. CORS ──
def test_cors_solo_para_angular_en_desarrollo(client):
    preflight = {"origin": "http://localhost:4200", "access-control-request-method": "POST"}
    r = client.options("/catalogo/libros/nuevo/", headers=preflight)
    assert r["access-control-allow-origin"] == "http://localhost:4200"

    r = client.options(
        "/catalogo/libros/nuevo/", headers={**preflight, "origin": "https://malo.example"}
    )
    assert "access-control-allow-origin" not in r


# ── 3. CSP ──
def test_csp_report_only_con_nonce(admin_client):
    r = admin_client.get("/admin/prestamos/prestamo/estadisticas/")
    cabecera = r["content-security-policy-report-only"]
    assert "script-src 'self' 'nonce-" in cabecera and "report-uri /csp-report/" in cabecera
    nonce = cabecera.split("'nonce-")[1].split("'")[0]
    assert (
        f'<script nonce="{nonce}">' in r.text
    )  # el script de la plantilla lleva el de ESTA respuesta


def test_csp_report_se_registra(client, caplog):
    informe = {
        "csp-report": {
            "document-uri": "http://localhost:8000/admin/",
            "violated-directive": "script-src-elem",
            "blocked-uri": "inline",
        }
    }
    r = client.post("/csp-report/", json.dumps(informe), content_type="application/csp-report")
    assert r.status_code == 204
    assert "CSP: script-src-elem bloqueó inline en http://localhost:8000/admin/" in caplog.text


# ── 1. check --deploy con prod.py ──
def test_check_deploy_sin_avisos():
    entorno = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.prod",
        "DJANGO_SECRET_KEY": secrets.token_urlsafe(50),
        "DJANGO_ALLOWED_HOSTS": "biblioteca.example.com",
        "SMTP_HOST": "smtp.example.com",
    }
    r = subprocess.run(
        [sys.executable, "manage.py", "check", "--deploy", "--fail-level", "WARNING"],
        cwd=settings.BASE_DIR,
        env=entorno,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "no issues" in r.stdout


def test_check_deploy_detecta_una_clave_debil():
    entorno = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.prod",
        "DJANGO_SECRET_KEY": "django-insecure-cambiame",
        "DJANGO_ALLOWED_HOSTS": "biblioteca.example.com",
        "SMTP_HOST": "smtp.example.com",
    }
    r = subprocess.run(
        [sys.executable, "manage.py", "check", "--deploy", "--fail-level", "WARNING"],
        cwd=settings.BASE_DIR,
        env=entorno,
        capture_output=True,
        text=True,
    )
    assert r.returncode != 0 and "security.W009" in r.stderr + r.stdout
