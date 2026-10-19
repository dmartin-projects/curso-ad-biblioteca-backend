"""Ejercicio del módulo 27: cliente de Open Library, circuit breaker, tarea y acción del admin."""

from datetime import date, timedelta

import httpx
import pytest
import respx
import time_machine
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.urls import reverse
from django.utils import timezone
from tenacity import wait_none

from catalogo.clients.openlibrary import DatosLibro, OpenLibraryClient, OpenLibraryError
from catalogo.models import Libro
from catalogo.tasks import breaker_openlibrary, completar_desde_openlibrary
from core.circuit_breaker import CircuitBreaker, CircuitoAbierto
from usuarios.models import Usuario

pytestmark = pytest.mark.django_db
BASE = "https://openlibrary.test"
ISBN = "9780441172719"
DUNE = {"title": " Dune ", "number_of_pages": 412, "publish_date": "June 1990", "authors": []}


@pytest.fixture(autouse=True)
def sin_esperas(monkeypatch, settings):
    """Sin esperas entre reintentos y con una URL que nunca es la real."""
    monkeypatch.setattr(OpenLibraryClient._get.retry, "wait", wait_none())
    settings.OPENLIBRARY_URL = BASE


@pytest.fixture
def cliente():
    return OpenLibraryClient(httpx.Client(base_url=BASE))


# ── 1 y 4. Cliente ──
@respx.mock
def test_buscar_isbn_ok_y_cacheado(cliente):
    ruta = respx.get(f"{BASE}/isbn/{ISBN}.json").respond(200, json=DUNE)
    libro = cliente.buscar_isbn(ISBN)
    assert libro == DatosLibro(isbn=ISBN, titulo="Dune", autores=[], paginas=412, anio=1990)
    cliente.buscar_isbn(ISBN)
    assert ruta.call_count == 1  # la segunda, de la caché


@respx.mock
def test_404_devuelve_none_y_se_cachea(cliente):
    ruta = respx.get(url__regex=r".*/isbn/.*").respond(404)
    assert cliente.buscar_isbn("9780000000002") is None
    assert cliente.buscar_isbn("9780000000002") is None
    assert ruta.call_count == 1  # caché negativa


@respx.mock
def test_timeout_reintenta_3_veces_y_falla(cliente):
    ruta = respx.get(url__regex=r".*/isbn/.*").mock(side_effect=httpx.ConnectTimeout("lento"))
    with pytest.raises(OpenLibraryError, match="no responde"):
        cliente.buscar_isbn(ISBN)
    assert ruta.call_count == 3


@respx.mock
def test_503_transitorio_se_recupera(cliente):
    ruta = respx.get(url__regex=r".*/isbn/.*").mock(
        side_effect=[httpx.Response(503), httpx.Response(429), httpx.Response(200, json=DUNE)]
    )
    assert cliente.buscar_isbn(ISBN).titulo == "Dune"
    assert ruta.call_count == 3


@respx.mock
def test_400_no_se_reintenta(cliente):
    ruta = respx.get(url__regex=r".*/isbn/.*").respond(400)
    with pytest.raises(OpenLibraryError, match="400"):
        cliente.buscar_isbn(ISBN)
    assert ruta.call_count == 1  # un 4xx no mejora reintentando


@respx.mock
def test_campos_ausentes_o_raros(cliente):
    respx.get(url__regex=r".*/isbn/.*").respond(
        200,
        json={"number_of_pages": "muchas", "publish_date": "s. f.", "authors": [{"key": "/a/1"}]},
    )
    libro = cliente.buscar_isbn(ISBN)
    assert libro == DatosLibro(isbn=ISBN, titulo="", autores=["/a/1"], paginas=None, anio=None)


# ── 3. Circuit breaker ──
def test_tras_5_fallos_deja_de_llamar():
    breaker = CircuitBreaker("prueba", umbral=5, enfriamiento=60)
    llamadas = 0

    def caida():
        nonlocal llamadas
        llamadas += 1
        raise OpenLibraryError("caída")

    for _ in range(5):
        with pytest.raises(OpenLibraryError):
            breaker.llamar(caida)
    with pytest.raises(CircuitoAbierto):  # el 6.º falla rápido…
        breaker.llamar(caida)
    assert llamadas == 5  # …sin llamar


def test_un_exito_reinicia_el_contador():
    breaker = CircuitBreaker("prueba", umbral=3)
    for _ in range(2):
        with pytest.raises(ValueError):
            breaker.llamar(int, "x")
    assert breaker.llamar(int, "7") == 7
    for _ in range(2):
        with pytest.raises(ValueError):
            breaker.llamar(int, "x")
    assert breaker.llamar(int, "8") == 8  # nunca se llegó a 3 seguidos


def test_semiabierto_deja_pasar_una_sola_prueba():
    breaker = CircuitBreaker("prueba", umbral=2, enfriamiento=60)
    for _ in range(2):
        with pytest.raises(ValueError):
            breaker.llamar(int, "x")  # abre
    inicio = timezone.now()

    def prueba_que_falla():
        with pytest.raises(CircuitoAbierto):  # mientras se prueba, el resto falla rápido
            breaker.llamar(int, "1")
        raise ValueError("sigue caída")

    with time_machine.travel(inicio + timedelta(seconds=61), tick=False):  # enfriado
        with pytest.raises(ValueError):
            breaker.llamar(prueba_que_falla)
        with pytest.raises(CircuitoAbierto):  # una prueba fallida basta para volver a abrir
            breaker.llamar(int, "1")
    with time_machine.travel(inicio + timedelta(seconds=122), tick=False):
        assert breaker.llamar(int, "7") == 7  # la prueba sale bien: cerrado…
        assert breaker.llamar(int, "8") == 8  # …y pasan todas


# ── 2. Tarea y acción del admin ──
@respx.mock
def test_tarea_rellena_solo_huecos():
    respx.get(f"{BASE}/isbn/{ISBN}.json").respond(200, json=DUNE)
    libro = Libro.objects.create(titulo="Dune", isbn=ISBN, paginas=500)
    assert completar_desde_openlibrary.delay(libro.pk).get() == "actualizado: publicado"
    libro.refresh_from_db()
    assert libro.paginas == 500  # el dato editado a mano se respeta
    assert libro.publicado == date(1990, 1, 1)


def test_tarea_con_circuito_abierto_reintenta_mas_tarde(mocker, celery_sin_propagar):
    libro = Libro.objects.create(titulo="Dune", isbn=ISBN)
    mocker.patch.object(breaker_openlibrary, "llamar", side_effect=CircuitoAbierto("cb"))
    retry = mocker.spy(completar_desde_openlibrary, "retry")
    completar_desde_openlibrary.apply(args=[libro.pk])
    assert retry.call_args.kwargs["countdown"] == 120


def test_accion_del_admin_encola_una_tarea_por_libro(
    client, mocker, django_capture_on_commit_callbacks
):
    admin = Usuario.objects.create_superuser("admin@example.com", password="x")
    client.force_login(admin)
    libros = [
        Libro.objects.create(titulo="Dune", isbn=ISBN),
        Libro.objects.create(titulo="Hyperion", isbn="9788498003253"),
    ]
    delay = mocker.patch("catalogo.admin.tarea_completar.delay")
    with django_capture_on_commit_callbacks(execute=True):
        r = client.post(
            reverse("admin:catalogo_libro_changelist"),
            {
                "action": "completar_desde_openlibrary",
                ACTION_CHECKBOX_NAME: [libro.pk for libro in libros],
            },
            follow=True,
        )
    assert "2 libro(s) en cola" in r.text
    assert sorted(c.args[0] for c in delay.call_args_list) == sorted(lb.pk for lb in libros)
