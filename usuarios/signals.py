from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import PerfilSocio


@receiver(post_save, sender=settings.AUTH_USER_MODEL, dispatch_uid="crear_perfil_socio")
def crear_perfil(sender, instance, created, raw, **kwargs):
    if not created or raw:
        return
    # el número sale del pk: único y sin carreras (dos altas simultáneas nunca comparten pk)
    PerfilSocio.objects.create(usuario=instance, numero=f"S-{instance.pk:06d}")
