import logging

from django.db import transaction
from django.dispatch import receiver

from prestamos.signals import prestamo_devuelto, prestamo_vencido

from .services import notificar_bibliotecarios

logger = logging.getLogger(__name__)


@receiver(prestamo_devuelto, dispatch_uid="notificaciones_devolucion")
def avisar_devolucion(sender, prestamo, **kwargs):
    # más adelante: avisar a la lista de espera del libro (con on_commit + una tarea, módulo 26)
    logger.info("Préstamo %s devuelto: %s", prestamo.pk, prestamo.ejemplar.libro)
    datos = {
        "evento": "prestamo_devuelto",
        "prestamo_id": prestamo.pk,
        "mensaje": f"Devuelto «{prestamo.ejemplar.libro.titulo}» ({prestamo.ejemplar.codigo})",
    }
    # módulo 25: aviso en tiempo real, solo si la devolución llega a confirmarse
    transaction.on_commit(lambda: notificar_bibliotecarios(datos))


@receiver(prestamo_vencido, dispatch_uid="notificaciones_vencido")
def avisar_vencido(sender, prestamo, dias_retraso, **kwargs):
    logger.info(
        "Préstamo %s vencido hace %s días (socio %s)", prestamo.pk, dias_retraso, prestamo.socio
    )
