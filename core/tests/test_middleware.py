"""Ejercicio del módulo 16."""

import logging

import pytest
from django.core.cache import cache

from core.middleware import PeticionesLentasMiddleware
from usuarios.models import Usuario

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def cache_limpia():
    cache.clear()
    yield
    cache.clear()


def test_cabeceras_de_id_y_tiempo(client):
    r = client.get("/health/")
    assert len(r["X-Request-ID"]) == 32  # uuid4().hex
    assert r["Server-Timing"].startswith("app;dur=")
    r = client.get("/health/", headers={"X-Request-ID": "abc-123"})
    assert r["X-Request-ID"] == "abc-123"  # se respeta el del proxy/cliente


def test_modo_mantenimiento(client):
    cache.set("modo_mantenimiento", True)
    r = client.get("/catalogo/libros/")
    assert r.status_code == 503 and r["Retry-After"] == "300"
    assert client.get("/health/").status_code == 200
    assert client.get("/admin/login/").status_code == 200
    cache.delete("modo_mantenimiento")
    assert client.get("/catalogo/libros/").status_code == 200


def test_registra_peticiones_lentas(client, caplog, monkeypatch):
    monkeypatch.setattr(PeticionesLentasMiddleware, "UMBRAL_MS", -1)  # todas "lentas"
    usuario = Usuario.objects.create_user("ana@example.com")
    client.force_login(usuario)
    with caplog.at_level(logging.WARNING, logger="rendimiento"):
        r = client.get("/catalogo/libros/")
    assert "Petición lenta GET /catalogo/libros/" in caplog.text
    assert f"usuario={usuario.pk} id={r['X-Request-ID']}" in caplog.text
