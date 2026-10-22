# mensajeria/management/commands/consumir_notificaciones.py
"""manage.py consumir_notificaciones: un servicio más en Docker, como los workers de Celery."""

from django.conf import settings
from django.core.management.base import BaseCommand
from kombu import Connection

from mensajeria.consumidor import Consumidor
from mensajeria.topologia import NOTIFICACIONES, declarar
from prestamos.notificaciones import notificar_evento  # lo que hace tu app con cada evento


class Command(BaseCommand):
    help = "Consume los eventos de préstamos de RabbitMQ (Ctrl+C o SIGTERM para parar)."

    def handle(self, *args, **opciones):
        with Connection(settings.EVENTOS_BROKER_URL, heartbeat=30) as conexion:
            declarar(conexion)
            consumidor = Consumidor(conexion, NOTIFICACIONES, notificar_evento, prefetch=10)
            try:
                consumidor.run()  # bloquea; reconecta solo si RabbitMQ se reinicia
            except KeyboardInterrupt:
                consumidor.should_stop = True
