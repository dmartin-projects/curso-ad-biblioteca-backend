"""Ejercicio del módulo 13 (3): enlace firmado de renovación."""

import pytest
import time_machine
from django.test import RequestFactory
from django.utils import timezone

from catalogo.models import Ejemplar, Libro
from prestamos.models import Prestamo
from prestamos.views import generar_enlace_renovacion
from usuarios.models import Usuario

pytestmark = pytest.mark.django_db


@pytest.fixture
def prestamo():
    libro = Libro.objects.create(titulo="Dune", isbn="9788497593793")
    ejemplar = Ejemplar.objects.create(libro=libro, codigo="D1")
    socio = Usuario.objects.create_user("ana@example.com")
    return Prestamo.objects.create(
        ejemplar=ejemplar, socio=socio, fecha_limite=timezone.now() + Prestamo.DURACION
    )


def test_renovar_con_enlace_firmado(client, prestamo):
    enlace = generar_enlace_renovacion(RequestFactory().get("/"), prestamo)
    assert enlace.startswith("http://testserver/prestamos/renovar/")
    limite = prestamo.fecha_limite
    r = client.get(enlace)  # lo que hace un cliente de correo al analizar el enlace
    assert r.status_code == 200 and r.json()["libro"] == "Dune"
    prestamo.refresh_from_db()
    assert prestamo.fecha_limite == limite  # el GET no renueva
    assert client.post(enlace).status_code == 200  # el botón de la página de confirmación
    prestamo.refresh_from_db()
    assert prestamo.fecha_limite == limite + Prestamo.DURACION


def test_enlace_manipulado_o_caducado(client, prestamo):
    enlace = generar_enlace_renovacion(RequestFactory().get("/"), prestamo)
    assert client.get(enlace[:-3] + "xyz/").status_code == 400  # firma rota
    with time_machine.travel(timezone.now() + timezone.timedelta(hours=25)):
        assert client.get(enlace).json() == {"error": "El enlace ha caducado"}


def test_el_enlace_vale_una_sola_vez(client, prestamo):
    enlace = generar_enlace_renovacion(RequestFactory().get("/"), prestamo)
    assert client.post(enlace).status_code == 200
    r = client.post(enlace)  # el mismo enlace otra vez: la fecha límite firmada ya no coincide
    assert r.status_code == 410 and r.json() == {"error": "Este enlace ya se ha usado"}


def test_un_prestamo_vencido_no_se_renueva(client, prestamo):
    prestamo.fecha_limite = timezone.now() + timezone.timedelta(hours=1)  # vence dentro de 1 h
    prestamo.save(update_fields=["fecha_limite"])
    enlace = generar_enlace_renovacion(RequestFactory().get("/"), prestamo)
    with time_machine.travel(timezone.now() + timezone.timedelta(hours=2)):
        r = client.post(enlace)  # el enlace aún vale (24 h), pero el préstamo ya ha vencido
    assert r.status_code == 409
    assert r.json() == {"error": "Un préstamo vencido no se renueva: devuélvelo."}
