# prestamos/tasks.py
import logging
from datetime import timedelta
from smtplib import SMTPException

from celery import shared_task
from django.tasks import task
from django.utils import timezone

from .emails import enviar_confirmacion
from .emails import enviar_recordatorio as componer_y_enviar_recordatorio
from .models import Multa, Prestamo
from .multas import importe_multa

logger = logging.getLogger(__name__)


# ── Parte A: django.tasks (cola en la BD, manage.py db_worker) ──
@task(queue_name="emails", priority=10)
def enviar_confirmacion_prestamo(prestamo_id: int) -> None:
    prestamo = Prestamo.objects.select_related("socio", "ejemplar__libro").get(pk=prestamo_id)
    enviar_confirmacion(prestamo)


# ── Parte B: Celery ──
@shared_task(
    bind=True,
    autoretry_for=(SMTPException, ConnectionError),  # ConnectionRefusedError: Mailpit parado
    retry_backoff=5,  # espera máxima 5, 10, 20, 40… s; el jitter elige un valor al azar hasta ahí
    retry_backoff_max=600,
    max_retries=8,  # cubre una caída de varios minutos (con True y 5 reintentos, unos segundos)
)
def enviar_recordatorio(self, prestamo_id: int) -> str:
    prestamo = Prestamo.objects.activos().filter(pk=prestamo_id).first()
    if prestamo is None:  # ya devuelto o borrado: nada que hacer
        logger.info("Préstamo %s ya no está activo", prestamo_id)
        return "no activo"
    componer_y_enviar_recordatorio(prestamo.socio, [prestamo])
    return "enviado"


@shared_task
def enviar_recordatorios_vencimiento(dias: int = 2) -> int:
    """Coordinadora: NO envía nada; encola una tarea por préstamo (se reparten entre workers)."""
    ahora = timezone.now()
    ids = list(
        Prestamo.objects.activos()
        .filter(fecha_limite__range=(ahora, ahora + timedelta(days=dias)))
        .values_list("pk", flat=True)
    )
    for prestamo_id in ids:
        enviar_recordatorio.delay(prestamo_id)
    return len(ids)


@shared_task
def calcular_multas() -> int:
    """Idempotente: ejecutarla dos veces la misma noche deja las mismas multas."""
    ahora = timezone.now()
    n = 0
    for prestamo in Prestamo.objects.vencidos().select_related(None).only("pk", "fecha_limite"):
        importe = importe_multa(prestamo.fecha_limite, ahora)  # la misma regla que devolver()
        multa, creada = Multa.objects.get_or_create(
            prestamo=prestamo, defaults={"importe_base": importe}
        )
        if not creada and not multa.pagada:
            multa.importe_base = importe  # crece cada día hasta que la paga
            multa.save(update_fields=["importe_base"])
        n += 1
    return n
