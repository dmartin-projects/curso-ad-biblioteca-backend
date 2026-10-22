# mensajeria/consumidor.py
"""Consumidor de eventos con kombu (módulo 26, Parte C): ack manual, prefetch y reintentos."""

import logging
from collections.abc import Callable

from kombu import Connection, Producer
from kombu.mixins import ConsumerMixin

from .topologia import APARCADOS, MAX_INTENTOS

log = logging.getLogger(__name__)


def intentos(mensaje) -> int:
    """Cuántas veces se ha intentado ya: RabbitMQ lo apunta en la cabecera x-death."""
    muertes = (mensaje.headers or {}).get("x-death") or []
    return 1 + sum(m["count"] for m in muertes if m.get("reason") == "rejected")


class Consumidor(ConsumerMixin):
    """ConsumerMixin pone el bucle y la reconexión; la subclase, las colas y qué hacer con cada una.

    Es un mixin como los de las vistas de Django (módulo 4): la base aporta lo genérico (run(),
    reconectar, parar limpio con should_stop) y pide dos cosas: get_consumers() y el callback.
    """

    def __init__(self, conexion: Connection, cola, manejar: Callable[[dict], None], *, prefetch=10):
        self.connection = conexion  # el nombre que exige ConsumerMixin
        self.cola = cola
        self.manejar = manejar
        self.prefetch = prefetch
        # En producción, una tabla con UNIQUE(message_id) (idempotencia, §12): un set no sobrevive
        # a un reinicio ni se comparte entre réplicas
        self.vistos: set[str] = set()

    def get_consumers(self, Consumer, channel):
        # prefetch_count: como mucho N mensajes sin confirmar en este proceso. Sin límite, RabbitMQ
        # le mandaría TODA la cola a un consumidor lento y los demás se quedarían mirando.
        return [
            Consumer(
                queues=[self.cola],
                callbacks=[self.al_recibir],
                accept=["json"],
                prefetch_count=self.prefetch,
            )
        ]

    def al_recibir(self, cuerpo: dict, mensaje) -> None:
        id_evento = mensaje.properties.get("message_id")
        if id_evento in self.vistos:
            # Entrega duplicada (RabbitMQ garantiza "al menos una vez"): ya hecho, se confirma y ya
            mensaje.ack()
            return
        try:
            self.manejar(cuerpo)
        except Exception:
            n = intentos(mensaje)
            if n < MAX_INTENTOS:
                log.warning("Evento %s falló (intento %d de %d)", id_evento, n, MAX_INTENTOS)
                # → x-dead-letter-exchange → <cola>.reintento → vuelve a la cola en 2 s
                mensaje.reject(requeue=False)
                return
            log.exception("Evento %s aparcado tras %d intentos", id_evento, n)
            Producer(mensaje.channel).publish(
                cuerpo,
                exchange=APARCADOS,
                routing_key="",
                headers={**(mensaje.headers or {}), "intentos": n},
                message_id=id_evento,
                delivery_mode=2,
                serializer="json",
            )
            mensaje.ack()  # fuera de la cola de trabajo: ya está a salvo en biblioteca.aparcados
            return
        self.vistos.add(id_evento)
        # ack SOLO después de hacer el trabajo: si el proceso muere antes, RabbitMQ lo reentrega
        mensaje.ack()
