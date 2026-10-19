"""Ejercicio del módulo 30: request_id en logs y en Celery, JSON, health checks y Sentry."""

import json
import logging
from types import SimpleNamespace

import pytest
import sentry_sdk
from django.db import connection
from django.http import HttpResponse
from django.urls import path
from pythonjsonlogger.json import JsonFormatter

from core.celery_signals import anadir_request_id, limpiar_request_id, recuperar_request_id
from core.logging import RequestIdFilter
from core.middleware import request_id_var

pytestmark = pytest.mark.django_db


def vista_que_registra(request):
    logging.getLogger("prestamos.services").info("Préstamo solicitado")
    return HttpResponse("ok")


def vista_que_falla(request):
    raise ZeroDivisionError("ups")


urlpatterns = [path("registra/", vista_que_registra), path("falla/", vista_que_falla)]


# ── 2. El id de petición en cada línea de log ──
@pytest.mark.urls(__name__)
def test_el_log_lleva_el_id_de_la_peticion(client, caplog):
    caplog.handler.addFilter(RequestIdFilter())  # como el handler "consola" de LOGGING
    r = client.get("/registra/", headers={"x-request-id": "angular-1234"})
    assert r["X-Request-ID"] == "angular-1234"
    (registro,) = [x for x in caplog.records if x.name == "prestamos.services"]
    assert registro.request_id == "angular-1234"


@pytest.mark.urls(__name__)
def test_un_id_malicioso_se_sustituye(client):
    r = client.get("/registra/", headers={"x-request-id": "x\nINFO falso: admin ha entrado"})
    assert len(r["X-Request-ID"]) == 32 and "\n" not in r["X-Request-ID"]  # uno nuevo


def test_fuera_de_una_peticion_el_id_es_un_guion():
    registro = logging.LogRecord("x", logging.INFO, __file__, 1, "hola", None, None)
    RequestIdFilter().filter(registro)
    assert registro.request_id == "-"


def test_formato_json_con_campos_extra():
    formato = JsonFormatter("%(asctime)s %(levelname)s %(name)s %(request_id)s %(message)s")
    registro = logging.LogRecord(
        "tickets.tasks", logging.INFO, __file__, 1, "Ticket procesado", None, None
    )
    registro.request_id = "abc"
    registro.ticket_id = 42  # lo que añade extra={"ticket_id": 42}
    linea = json.loads(formato.format(registro))
    assert linea["request_id"] == "abc" and linea["ticket_id"] == 42
    assert linea["message"] == "Ticket procesado" and linea["levelname"] == "INFO"


# ── 2. Propagación a Celery (las signals, sin broker) ──
def test_el_id_viaja_en_las_cabeceras_y_se_recupera_en_el_worker():
    token = request_id_var.set("peticion-7")  # estamos "dentro" de la petición
    cabeceras = {}
    anadir_request_id(headers=cabeceras)
    request_id_var.reset(token)
    assert cabeceras == {"request_id": "peticion-7"}

    # en el worker, las cabeceras propias llegan como atributos de task.request
    tarea = SimpleNamespace(request=SimpleNamespace(request_id="peticion-7"))
    recuperar_request_id(task=tarea)
    assert request_id_var.get() == "peticion-7"
    limpiar_request_id(task=tarea)
    assert request_id_var.get() == "-"  # el siguiente mensaje no lo hereda


# ── 5. Health checks ──
def test_health_live_y_ready(client):
    assert client.get("/health/live/").json() == {"ok": True}
    assert client.get("/health/ready/").json() == {"db": "ok", "cache": "ok"}


def test_ready_da_503_sin_base_de_datos(client, mocker):
    mocker.patch.object(connection, "cursor", side_effect=Exception("BD caída"))
    r = client.get("/health/ready/")
    assert r.status_code == 503 and r.json() == {"db": "error", "cache": "ok"}
    assert client.get("/health/live/").status_code == 200  # el proceso sigue vivo


# ── 3. Sentry (sin cuenta: un transporte que guarda los eventos en una lista) ──
class TransporteDePrueba(sentry_sdk.transport.Transport):
    def __init__(self, options=None):
        super().__init__(options)
        self.eventos = []

    def capture_envelope(self, envelope):
        self.eventos += [item.payload.json for item in envelope.items if item.type == "event"]


@pytest.fixture
def sentry():
    transporte = TransporteDePrueba()
    sentry_sdk.init(dsn="https://clave@sentry.example/1", transport=transporte)
    yield transporte
    sentry_sdk.init()  # sin DSN: desactivado


@pytest.mark.urls(__name__)
def test_un_error_en_una_vista_llega_a_sentry(client, sentry):
    client.raise_request_exception = False
    assert client.get("/falla/", headers={"x-request-id": "rid-99"}).status_code == 500
    sentry_sdk.flush()
    (evento,) = sentry.eventos
    excepcion = evento["exception"]["values"][-1]
    assert excepcion["type"] == "ZeroDivisionError" and excepcion["value"] == "ups"
    assert evento["transaction"] == "/falla/"  # agrupa por ruta
    assert evento.get("user") is None  # sin datos personales: es lo que hace por defecto


def test_un_error_en_una_tarea_llega_a_sentry(sentry, celery_sin_propagar, mocker):
    from tickets.models import Ticket
    from tickets.tasks import procesar_ticket

    ticket = Ticket.objects.create(texto="ilegible")
    procesar_ticket.apply(args=[ticket.pk])  # ValueError dentro de la tarea
    sentry_sdk.flush()
    tipos = [e["exception"]["values"][-1]["type"] for e in sentry.eventos]
    assert "ValueError" in tipos
