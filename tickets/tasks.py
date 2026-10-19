# tickets/tasks.py
from celery import shared_task
from django.db import transaction
from django.db.models import F

from .ia import ErrorIA, extraer_con_ia
from .models import Gasto, Ticket


@shared_task(bind=True, autoretry_for=(ErrorIA,), retry_backoff=True, max_retries=4)
def procesar_ticket(self, ticket_id: int) -> str:
    # 1. Marca el estado de forma atómica: solo una ejecución "gana"
    actualizados = Ticket.objects.filter(
        pk=ticket_id, estado__in=[Ticket.Estado.PENDIENTE, Ticket.Estado.ERROR]
    ).update(estado=Ticket.Estado.PROCESANDO, intentos=F("intentos") + 1)
    if not actualizados:
        return "ya procesado o en proceso"

    ticket = Ticket.objects.get(pk=ticket_id)
    try:
        datos = extraer_con_ia(ticket.texto)
    except Exception:
        # Vuelve a ERROR para que un reintento (automático o manual) pueda "ganar" otra vez
        Ticket.objects.filter(pk=ticket_id).update(estado=Ticket.Estado.ERROR)
        raise

    with transaction.atomic():
        # 2. update_or_create con la clave natural (el ticket): repetirlo no duplica
        Gasto.objects.update_or_create(ticket=ticket, defaults=datos)
        ticket.estado = Ticket.Estado.PROCESADO
        ticket.save(update_fields=["estado"])
    return "procesado"
