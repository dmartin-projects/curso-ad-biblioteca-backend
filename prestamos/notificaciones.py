# prestamos/notificaciones.py
"""Qué hace la biblioteca con cada evento de préstamo que llega de RabbitMQ (módulo 26, Parte C).

Lo llama manage.py consumir_notificaciones: avisa al socio por WebSocket (módulo 25).
"""

from notificaciones.services import notificar_usuario


def notificar_evento(evento: dict) -> None:
    datos = evento.get("datos", {})
    if (socio := datos.get("socio")) is not None:
        notificar_usuario(socio, {"tipo": evento["tipo"], **datos})
