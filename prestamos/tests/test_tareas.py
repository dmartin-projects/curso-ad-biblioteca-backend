"""Ejercicio del módulo 26 (1-3): django.tasks, Celery con reintentos y tareas periódicas."""

from datetime import timedelta
from decimal import Decimal
from smtplib import SMTPServerDisconnected

import pytest
import time_machine
from django.tasks import TaskResultStatus, default_task_backend
from django.utils import timezone

from catalogo.models import Ejemplar, Libro
from prestamos.models import Multa, Prestamo
from prestamos.services import devolver, prestar
from prestamos.tasks import (
    calcular_multas,
    enviar_confirmacion_prestamo,
    enviar_recordatorio,
    enviar_recordatorios_vencimiento,
)
from usuarios.models import Usuario

pytestmark = pytest.mark.django_db


@pytest.fixture
def libro():
    return Libro.objects.create(titulo="Dune", isbn="9788497593793")


@pytest.fixture
def socio():
    return Usuario.objects.create_user("ana@example.com", nombre="Ana")


def nuevo_prestamo(libro, socio, codigo, vence_en: timedelta) -> Prestamo:
    return Prestamo.objects.create(
        ejemplar=Ejemplar.objects.create(libro=libro, codigo=codigo),
        socio=socio,
        fecha_limite=timezone.now() + vence_en,
    )


# ── 1. django.tasks ──
def test_prestar_encola_la_confirmacion(
    settings, django_capture_on_commit_callbacks, libro, socio, mailoutbox
):
    settings.TASKS = {
        "default": {
            "BACKEND": "django.tasks.backends.dummy.DummyBackend",  # guarda, no ejecuta
            "QUEUES": ["default", "emails"],
        }
    }
    ejemplar = Ejemplar.objects.create(libro=libro, codigo="D1")
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        prestamo = prestar(ejemplar.pk, socio)
    assert default_task_backend.results == []  # dentro de la transacción no se encola nada
    for callback in callbacks:  # el COMMIT (hay más: la invalidación de caché del módulo 23)
        callback()
    (resultado,) = default_task_backend.results
    assert resultado.task.name == "enviar_confirmacion_prestamo"
    assert resultado.task.queue_name == "emails"
    assert resultado.args == [prestamo.pk]  # un id, no el objeto
    assert mailoutbox == []  # DummyBackend no ejecuta


def test_la_tarea_envia_el_email(libro, socio, mailoutbox):
    prestamo = nuevo_prestamo(libro, socio, "D1", timedelta(days=21))
    resultado = enviar_confirmacion_prestamo.enqueue(prestamo.pk)  # ImmediateBackend
    assert resultado.status == TaskResultStatus.SUCCESSFUL
    assert mailoutbox[0].subject == "Préstamo confirmado: Dune"


# ── 2. Celery: reintentos ──
def test_recordatorio_reintenta_si_el_smtp_falla(
    celery_sin_propagar, mocker, libro, socio, mailoutbox
):
    prestamo = nuevo_prestamo(libro, socio, "D1", timedelta(days=1))
    enviar = mocker.patch(
        "prestamos.tasks.componer_y_enviar_recordatorio",
        side_effect=[ConnectionRefusedError, SMTPServerDisconnected, None],
    )
    # apply(): ejecuta aquí mismo y encadena los reintentos sin esperar el backoff
    resultado = enviar_recordatorio.apply(args=[prestamo.pk])
    assert resultado.get() == "enviado"
    assert enviar.call_count == 3


def test_recordatorio_se_rinde_tras_max_retries(celery_sin_propagar, mocker, libro, socio):
    prestamo = nuevo_prestamo(libro, socio, "D1", timedelta(days=1))
    enviar = mocker.patch(
        "prestamos.tasks.componer_y_enviar_recordatorio", side_effect=ConnectionRefusedError
    )
    with pytest.raises(ConnectionRefusedError):
        enviar_recordatorio.apply(args=[prestamo.pk]).get()
    assert enviar.call_count == 9  # 1 + max_retries=8


def test_recordatorio_de_prestamo_devuelto_no_envia(libro, socio, mailoutbox):
    prestamo = devolver(nuevo_prestamo(libro, socio, "D1", timedelta(days=1)))
    assert enviar_recordatorio.delay(prestamo.pk).get() == "no activo"
    assert mailoutbox == []


# ── 3. Periódicas ──
def test_coordinadora_encola_una_por_prestamo(mocker, libro, socio):
    pronto = nuevo_prestamo(libro, socio, "D1", timedelta(days=1))
    nuevo_prestamo(libro, socio, "D2", timedelta(days=10))  # aún lejos
    nuevo_prestamo(libro, socio, "D3", -timedelta(days=1))  # ya vencido: eso es otra tarea
    delay = mocker.patch("prestamos.tasks.enviar_recordatorio.delay")
    assert enviar_recordatorios_vencimiento() == 1
    delay.assert_called_once_with(pronto.pk)


def test_calcular_multas_es_idempotente_y_crece(libro, socio):
    prestamo = nuevo_prestamo(libro, socio, "D1", -timedelta(days=3, hours=1))
    nuevo_prestamo(libro, socio, "D2", timedelta(days=5))  # en plazo: sin multa

    assert calcular_multas() == 1
    assert calcular_multas() == 1  # dos veces la misma noche…
    assert Multa.objects.count() == 1  # …una sola multa
    assert Multa.objects.get().total == Decimal("1.50")

    with time_machine.travel(timezone.now() + timedelta(days=2)):
        calcular_multas()
    assert Multa.objects.get(prestamo=prestamo).total == Decimal("2.50")


def test_multa_pagada_no_cambia(libro, socio):
    prestamo = nuevo_prestamo(libro, socio, "D1", -timedelta(days=3, hours=1))
    Multa.objects.create(prestamo=prestamo, importe_base=Decimal("1.00"), pagada=True)
    calcular_multas()
    assert Multa.objects.get().importe_base == Decimal("1.00")


def test_beat_tiene_las_dos_programaciones(settings):
    programa = settings.CELERY_BEAT_SCHEDULE
    assert programa["calcular-multas"]["task"] == "prestamos.tasks.calcular_multas"
    assert programa["recordatorios-diarios"]["schedule"].hour == {9}
