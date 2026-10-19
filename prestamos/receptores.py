# prestamos/receptores.py — invalidar la caché al cambiar préstamos (módulo 23)
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .estadisticas import invalidar_estadisticas
from .models import Prestamo


@receiver([post_save, post_delete], sender=Prestamo, dispatch_uid="cache_estadisticas")
def invalidar_al_cambiar(sender, **kwargs):
    # on_commit: si borras antes del COMMIT, otra petición puede rellenar la caché con datos viejos
    transaction.on_commit(invalidar_estadisticas)
