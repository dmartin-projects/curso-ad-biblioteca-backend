import logging

from django.dispatch import receiver

from prestamos.signals import prestamo_devuelto, prestamo_vencido

logger = logging.getLogger(__name__)


@receiver(prestamo_devuelto, dispatch_uid="notificaciones_devolucion")
def avisar_devolucion(sender, prestamo, **kwargs):
    # más adelante: avisar a la lista de espera del libro (con on_commit + una tarea, módulo 26)
    logger.info("Préstamo %s devuelto: %s", prestamo.pk, prestamo.ejemplar.libro)


@receiver(prestamo_vencido, dispatch_uid="notificaciones_vencido")
def avisar_vencido(sender, prestamo, dias_retraso, **kwargs):
    logger.info(
        "Préstamo %s vencido hace %s días (socio %s)", prestamo.pk, dias_retraso, prestamo.socio
    )
