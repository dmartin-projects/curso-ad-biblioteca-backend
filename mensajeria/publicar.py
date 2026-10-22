# mensajeria/publicar.py
"""Publicar eventos de dominio en RabbitMQ (módulo 26, Parte C)."""

import uuid
from datetime import UTC, datetime

from django.conf import settings
from django.db import transaction
from kombu import Connection

from .topologia import EVENTOS


def publicar(tipo: str, datos: dict, *, url: str | None = None) -> str:
    """Publica YA un evento ('prestamo.creado'…) y espera a que el broker confirme que lo tiene.

    - delivery_mode=2 (persistente): se escribe a disco; un reinicio de RabbitMQ no lo pierde.
    - confirm_publish: publish() no vuelve hasta que RabbitMQ dice "lo tengo" (o lanza excepción).
    - message_id: los consumidores lo usan para no procesar dos veces el mismo evento.
    """
    id_evento = str(uuid.uuid4())
    opciones = {"confirm_publish": True}
    with Connection(url or settings.EVENTOS_BROKER_URL, transport_options=opciones) as conexion:
        conexion.Producer().publish(
            {"tipo": tipo, "datos": datos, "fecha": datetime.now(UTC).isoformat()},
            exchange=EVENTOS,
            routing_key=tipo,  # el topic enruta por aquí: prestamo.creado, socio.alta…
            declare=[EVENTOS],
            serializer="json",
            delivery_mode=2,
            message_id=id_evento,
            retry=True,  # si la conexión se ha caído, reconecta y reintenta (hasta 3 veces)
            retry_policy={"max_retries": 3, "interval_start": 0.5, "interval_step": 1},
        )
    return id_evento


def publicar_al_confirmar(tipo: str, datos: dict) -> None:
    """Lo que se llama desde los servicios: el evento sale SOLO si la transacción se confirma.

    Sin on_commit, un rollback dejaría en la cola un 'prestamo.creado' de un préstamo que no existe.
    Y si el proceso muere justo entre el COMMIT y el publish, el evento se pierde: para no perder
    ninguno hace falta el patrón outbox (módulo 85).
    """
    transaction.on_commit(lambda: publicar(tipo, datos))
