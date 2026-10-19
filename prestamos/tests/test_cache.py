"""Ejercicio del módulo 23: caché de estadísticas, versionado del catálogo y estampida."""

import threading
import time
from datetime import timedelta

import pytest
import redis
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from catalogo.models import Autor, Ejemplar, Libro
from core.cache import con_cerrojo
from prestamos.estadisticas import CLAVE_ESTADISTICAS, estadisticas_prestamos
from prestamos.models import Prestamo
from prestamos.services import devolver
from usuarios.models import Usuario

pytestmark = pytest.mark.django_db


@pytest.fixture
def libro():
    return Libro.objects.create(titulo="Dune", isbn="9788497593793")


@pytest.fixture
def socio():
    return Usuario.objects.create_user("ana@example.com")


def prestar(libro, socio, codigo, dias=21):
    ejemplar = Ejemplar.objects.create(libro=libro, codigo=codigo)
    return Prestamo.objects.create(
        ejemplar=ejemplar, socio=socio, fecha_limite=timezone.now() + timedelta(days=dias)
    )


# ── 2. Estadísticas: get_or_set + invalidación con signals ──
def test_estadisticas_se_cachean(django_assert_num_queries, libro, socio):
    prestar(libro, socio, "D1")
    with django_assert_num_queries(3):  # activos, vencidos, por_mes
        primera = estadisticas_prestamos()
    with django_assert_num_queries(0):  # de la caché
        assert estadisticas_prestamos() == primera
    assert primera["activos"] == 1
    assert primera["por_mes"][0]["total"] == 1


def test_crear_y_devolver_invalidan(django_capture_on_commit_callbacks, libro, socio):
    assert estadisticas_prestamos()["activos"] == 0
    with django_capture_on_commit_callbacks(execute=True):
        prestamo = prestar(libro, socio, "D1")
    assert cache.get(CLAVE_ESTADISTICAS) is None  # borrada al confirmar
    assert estadisticas_prestamos()["activos"] == 1

    with django_capture_on_commit_callbacks(execute=True):
        devolver(prestamo)
    assert estadisticas_prestamos()["activos"] == 0


def test_sin_commit_no_se_invalida(django_capture_on_commit_callbacks, libro, socio):
    estadisticas_prestamos()
    with django_capture_on_commit_callbacks(execute=False):
        prestar(libro, socio, "D1")
    assert cache.get(CLAVE_ESTADISTICAS) is not None  # hasta el COMMIT, nada


# ── 3. Versionado del catálogo ──
def test_listado_cacheado_por_filtros_e_invalidado(client, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        dune = Libro.objects.create(titulo="Dune", isbn="9788497593793")
        dune.autores.add(Autor.objects.create(nombre="Frank Herbert", slug="herbert"))
    url = reverse("catalogo:lista_libros_cbv")

    with CaptureQueriesContext(connection) as consultas:
        assert client.get(url).json()["count"] == 1
    assert len(consultas) > 0
    with CaptureQueriesContext(connection) as consultas:
        assert client.get(url).json()["count"] == 1
    assert len(consultas) == 0  # misma URL → caché
    with CaptureQueriesContext(connection) as consultas:
        client.get(url, {"q": "dune"})
    assert len(consultas) > 0  # otros filtros → otra clave

    with django_capture_on_commit_callbacks(execute=True):
        Libro.objects.create(titulo="Hyperion", isbn="9788498003253")
    assert client.get(url).json()["count"] == 2  # nueva versión → recalcula

    with django_capture_on_commit_callbacks(execute=True):
        Autor.objects.filter(slug="herbert").update(nombre="F. Herbert")  # update(): sin signals
    assert "Frank Herbert" in str(client.get(url).json())  # ⚠️ la caché no se ha enterado

    with django_capture_on_commit_callbacks(execute=True):
        autor = Autor.objects.get(slug="herbert")
        autor.save()  # save() sí dispara post_save → nueva versión
    assert "F. Herbert" in str(client.get(url).json())


def test_orden_de_parametros_no_duplica_claves(client):
    url = reverse("catalogo:lista_libros_cbv")
    client.get(url + "?q=a&desde=2000")
    with CaptureQueriesContext(connection) as consultas:
        client.get(url + "?desde=2000&q=a")
    assert len(consultas) == 0


# ── 5. Estampida ──
def simular_estampida(obtener, hilos=50) -> int:
    calculos = 0
    candado = threading.Lock()

    def calcular():
        nonlocal calculos
        with candado:
            calculos += 1
        time.sleep(0.2)  # una consulta lenta
        return {"total": 42}

    barrera = threading.Barrier(hilos)

    def peticion():
        barrera.wait()  # todos a la vez, con la caché vacía
        assert obtener("estampida", calcular) == {"total": 42}

    trabajadores = [threading.Thread(target=peticion) for _ in range(hilos)]
    for t in trabajadores:
        t.start()
    for t in trabajadores:
        t.join()
    return calculos


def sin_cerrojo(clave, calcular):
    valor = cache.get(clave)
    if valor is None:
        valor = calcular()
        cache.set(clave, valor, 600)
    return valor


def test_estampida_con_y_sin_cerrojo():
    sin = simular_estampida(sin_cerrojo)
    cache.clear()
    con = simular_estampida(con_cerrojo)
    print(f"\nsin cerrojo: {sin} cálculos · con cerrojo: {con}")
    assert sin > 10
    assert con == 1


# ── 1 y 4. Redis de verdad (se salta si no está levantado) ──
def redis_disponible() -> bool:
    try:
        return redis.Redis.from_url("redis://localhost:6379/1").ping()
    except redis.ConnectionError:
        return False


@pytest.mark.skipif(not redis_disponible(), reason="docker compose up -d redis")
def test_redis_real_prefijo_y_ttl(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": "redis://localhost:6379/1",
            "KEY_PREFIX": "biblioteca-test",
        }
    }
    from django.core.cache import cache as cache_redis

    cache_redis.set("estadisticas:prestamos", {"activos": 1}, timeout=600)
    r = redis.Redis.from_url("redis://localhost:6379/1")
    (clave,) = r.keys("biblioteca-test*")
    assert clave == b"biblioteca-test:1:estadisticas:prestamos"  # prefijo:versión:clave
    assert 590 < r.ttl(clave) <= 600
    cache_redis.delete("estadisticas:prestamos")


def test_sesiones_en_cache_con_respaldo_en_bd():
    assert settings.SESSION_ENGINE == "django.contrib.sessions.backends.cached_db"
