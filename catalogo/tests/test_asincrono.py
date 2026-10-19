"""Ejercicio del módulo 24: vistas asíncronas, llamadas en paralelo y SSE."""

import asyncio
import time
from datetime import timedelta

import httpx
import pytest
import respx
from asgiref.sync import async_to_sync
from django.test import AsyncClient
from django.urls import reverse
from django.utils import timezone

from catalogo.asincrono import GOOGLE_BOOKS, OPENLIBRARY, PORTADA
from catalogo.models import Ejemplar, Libro
from prestamos.models import Prestamo
from usuarios.models import Usuario

pytestmark = pytest.mark.django_db
ISBN = "9788497593793"


def lenta(respuesta: httpx.Response, segundos: float = 0.3):
    async def efecto(request):
        await asyncio.sleep(segundos)  # una API que tarda 300 ms
        return respuesta

    return efecto


@pytest.fixture
def apis():
    """Nunca llames a APIs reales en los tests: respx intercepta httpx."""
    with respx.mock(assert_all_called=False) as mock:
        mock.get(OPENLIBRARY.format(isbn=ISBN)).mock(
            side_effect=lenta(httpx.Response(200, json={"title": "Dune"}))
        )
        mock.get(GOOGLE_BOOKS).mock(side_effect=lenta(httpx.Response(200, json={"totalItems": 3})))
        mock.head(PORTADA.format(isbn=ISBN)).mock(side_effect=lenta(httpx.Response(200)))
        yield mock


def pedir(url, **kwargs):
    return async_to_sync(AsyncClient(**kwargs).get)(url)


def test_info_libro_en_paralelo(apis):
    Libro.objects.create(titulo="Dune", isbn=ISBN)
    pedir(reverse("catalogo:info_libro", args=[ISBN]))  # calentamiento: la 1.ª petición carga cosas
    inicio = time.perf_counter()
    r = pedir(reverse("catalogo:info_libro", args=[ISBN]))
    paralelo = time.perf_counter() - inicio
    assert r.json() == {
        "isbn": ISBN,
        "en_catalogo": True,
        "openlibrary": {"title": "Dune"},
        "google_books": 3,
        "tiene_portada": True,
    }

    inicio = time.perf_counter()
    pedir(reverse("catalogo:info_libro_secuencial", args=[ISBN]))
    secuencial = time.perf_counter() - inicio
    print(f"\nparalelo: {paralelo:.2f} s · secuencial: {secuencial:.2f} s")
    assert secuencial > 0.85  # tres esperas de 0,3 s, una detrás de otra: no puede bajar de ahí
    assert paralelo < secuencial / 2  # ~0,3 s frente a ~0,9 s; la razón aguanta una CI cargada


def test_una_api_caida_no_tumba_las_demas(apis):
    apis.get(GOOGLE_BOOKS).mock(side_effect=httpx.ConnectTimeout("sin respuesta"))
    apis.head(PORTADA.format(isbn=ISBN)).mock(return_value=httpx.Response(404))
    datos = pedir(reverse("catalogo:info_libro", args=[ISBN])).json()
    assert datos["en_catalogo"] is False
    assert datos["openlibrary"] == {"title": "Dune"}
    assert datos["google_books"] is None and datos["tiene_portada"] is False


def test_las_vistas_sincronas_siguen_funcionando_en_asgi():
    r = pedir(reverse("catalogo:lista_libros_cbv"))  # vista síncrona servida por el handler ASGI
    assert r.status_code == 200 and r.json()["count"] == 0


# ── SSE ──
def test_sse_requiere_sesion():
    assert pedir(reverse("prestamos:eventos")).status_code == 401


def test_sse_envia_los_prestamos_activos():
    socio = Usuario.objects.create_user("ana@example.com")
    libro = Libro.objects.create(titulo="Dune", isbn=ISBN)
    for codigo in ("D1", "D2"):
        Prestamo.objects.create(
            ejemplar=Ejemplar.objects.create(libro=libro, codigo=codigo),
            socio=socio,
            fecha_limite=timezone.now() + timedelta(days=21),
        )

    async def primer_evento():
        client = AsyncClient()
        await client.aforce_login(socio)
        r = await client.get(reverse("prestamos:eventos"))
        assert r["Content-Type"] == "text/event-stream"
        flujo = aiter(r.streaming_content)
        evento = await anext(flujo)  # el flujo es infinito: lee uno y corta
        await flujo.aclose()
        return evento

    assert async_to_sync(primer_evento)() == b'data: {"activos": 2}\n\n'
