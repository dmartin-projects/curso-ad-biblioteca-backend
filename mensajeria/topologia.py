# mensajeria/topologia.py
"""Exchanges y colas de los eventos de la biblioteca (módulo 26, Parte C).

Todo es durable (sobrevive a un reinicio de RabbitMQ) y los mensajes se publican persistentes.
"""

from kombu import Exchange, Queue, binding

EVENTOS = Exchange("biblioteca.eventos", type="topic", durable=True)
REINTENTOS = Exchange("biblioteca.reintentos", type="direct", durable=True)
APARCADOS = Exchange("biblioteca.aparcados", type="fanout", durable=True)

ESPERA_REINTENTO_MS = 2_000
MAX_INTENTOS = 3


def con_reintentos(nombre: str, *claves: str) -> tuple[Queue, Queue]:
    """Una cola de trabajo y su cola de espera: lo rechazado espera ahí y vuelve a la cola."""
    principal = Queue(
        nombre,
        bindings=[binding(EVENTOS, routing_key=clave) for clave in claves],
        durable=True,
        queue_arguments={
            "x-queue-type": "quorum",  # replicada: la recomendada en RabbitMQ 4
            # reject(requeue=False) → el mensaje va a este exchange, con esta clave
            "x-dead-letter-exchange": REINTENTOS.name,
            "x-dead-letter-routing-key": nombre,
        },
    )
    espera = Queue(
        f"{nombre}.reintento",
        exchange=REINTENTOS,
        routing_key=nombre,
        durable=True,
        queue_arguments={
            "x-message-ttl": ESPERA_REINTENTO_MS,
            # Al caducar, al exchange por defecto ("") con clave = su cola: vuelve SOLO a ella.
            # Si volviera a biblioteca.eventos, analitica.eventos (#) lo recibiría dos veces.
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": nombre,
        },
    )
    return principal, espera


NOTIFICACIONES, NOTIFICACIONES_ESPERA = con_reintentos("notificaciones.prestamos", "prestamo.*")
ANALITICA = Queue("analitica.eventos", exchange=EVENTOS, routing_key="#", durable=True)
APARCADOS_COLA = Queue("biblioteca.aparcados", exchange=APARCADOS, durable=True)

TODAS = [NOTIFICACIONES, NOTIFICACIONES_ESPERA, ANALITICA, APARCADOS_COLA]


def declarar(conexion) -> None:
    """Crea exchanges, colas y bindings si no existen (idempotente): al arrancar el consumidor."""
    canal = conexion.default_channel
    for cola in TODAS:
        cola(canal).declare()
