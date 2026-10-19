"""Ejercicio del módulo 26 (5): procesar_ticket es idempotente."""

from decimal import Decimal

import pytest

from tickets.ia import ErrorIA
from tickets.models import Gasto, Ticket
from tickets.tasks import procesar_ticket

pytestmark = pytest.mark.django_db


@pytest.fixture
def ticket():
    return Ticket.objects.create(texto="MERCADONA calle Mayor 1 TOTAL 23,45")


def test_dos_ejecuciones_un_solo_gasto(ticket):
    assert procesar_ticket(ticket.pk) == "procesado"
    assert procesar_ticket(ticket.pk) == "ya procesado o en proceso"  # acks_late la reentrega
    assert Gasto.objects.filter(ticket=ticket).count() == 1
    gasto = Gasto.objects.get()
    assert (gasto.comercio, gasto.importe) == ("MERCADONA", Decimal("23.45"))
    ticket.refresh_from_db()
    assert ticket.intentos == 1


def test_una_ejecucion_en_curso_no_se_duplica(ticket):
    Ticket.objects.filter(pk=ticket.pk).update(estado=Ticket.Estado.PROCESANDO)  # otro worker
    assert procesar_ticket(ticket.pk) == "ya procesado o en proceso"
    assert not Gasto.objects.exists()


def test_error_transitorio_reintenta_y_acaba_bien(celery_sin_propagar, mocker, ticket):
    mocker.patch(
        "tickets.tasks.extraer_con_ia",
        side_effect=[ErrorIA("503"), {"comercio": "DIA", "importe": Decimal("5.00")}],
    )
    assert procesar_ticket.apply(args=[ticket.pk]).get() == "procesado"
    ticket.refresh_from_db()
    assert (ticket.estado, ticket.intentos) == (Ticket.Estado.PROCESADO, 2)
    assert Gasto.objects.get().comercio == "DIA"


def test_error_de_datos_no_reintenta(celery_sin_propagar, mocker, ticket):
    Ticket.objects.filter(pk=ticket.pk).update(texto="ilegible")
    with pytest.raises(ValueError):
        procesar_ticket.apply(args=[ticket.pk]).get()
    ticket.refresh_from_db()
    assert (ticket.estado, ticket.intentos) == (Ticket.Estado.ERROR, 1)  # un intento, no cinco
