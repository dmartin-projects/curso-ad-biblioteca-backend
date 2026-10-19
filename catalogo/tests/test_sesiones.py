"""Ejercicio del módulo 13 (1 y 2)."""

import pytest
import redis

from catalogo.models import Libro

pytestmark = pytest.mark.django_db


@pytest.fixture
def libros():
    return [Libro.objects.create(titulo=f"Libro {i}", isbn=f"97884000000{i:02d}") for i in range(7)]


def test_vistos_recientemente(client, libros):
    assert client.get("/catalogo/recientes/").json() == {"results": []}
    for libro in [*libros[:6], libros[2]]:  # 6 distintos y vuelve al 2
        client.get(f"/catalogo/libros/{libro.pk}/")
    titulos = [x["titulo"] for x in client.get("/catalogo/recientes/").json()["results"]]
    assert titulos == ["Libro 2", "Libro 5", "Libro 4", "Libro 3", "Libro 1"]  # 5, sin repetir
    libros[5].delete()
    assert len(client.get("/catalogo/recientes/").json()["results"]) == 4
    # otro navegador (otra sesión) no ve nada
    from django.test import Client

    assert Client().get("/catalogo/recientes/").json() == {"results": []}


def redis_disponible() -> bool:
    try:
        return redis.Redis(db=9).ping()
    except redis.ConnectionError:
        return False


@pytest.mark.skipif(not redis_disponible(), reason="docker compose up -d redis")
def test_sesiones_en_cached_db(client, libros, settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": "redis://localhost:6379/9",
        }
    }
    settings.SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"
    client.get(f"/catalogo/libros/{libros[0].pk}/")
    claves = redis.Redis(db=9).keys("*")
    sesion = client.cookies["sessionid"].value
    assert any(
        sesion.encode() in clave for clave in claves
    )  # ":1:django.contrib.sessions.cached_db…<id>"
