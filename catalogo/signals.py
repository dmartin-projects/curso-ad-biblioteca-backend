from django.db import transaction
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save
from django.dispatch import receiver

from core.cache import subir_version

from .busqueda import actualizar_busqueda
from .models import Autor, Ejemplar, Libro


@receiver(post_save, sender=Libro, dispatch_uid="libro_actualizar_busqueda")
def libro_guardado(sender, instance, raw, **kwargs):
    if raw:  # loaddata: los datos llegan tal cual
        return
    actualizar_busqueda(instance.pk)


@receiver(m2m_changed, sender=Libro.autores.through, dispatch_uid="libro_autores_busqueda")
def autores_cambiados(sender, instance, action, reverse, pk_set, **kwargs):
    if action not in {"post_add", "post_remove", "post_clear"}:
        return
    if reverse:  # autor.libros.add(libro): instance es el Autor y pk_set, los libros
        for libro_id in pk_set or []:
            actualizar_busqueda(libro_id)
    else:
        actualizar_busqueda(instance.pk)


@receiver(post_save, sender=Autor, dispatch_uid="autor_renombrado_busqueda")
def autor_guardado(sender, instance, created, raw, **kwargs):
    if created or raw:
        return
    for libro_id in instance.libros.values_list("pk", flat=True):  # su nombre está en el vector
        actualizar_busqueda(libro_id)


# ── módulo 20: no dejar archivos huérfanos en el almacenamiento ──
CAMPOS_ARCHIVO = ("portada", "ficha_pdf")


@receiver(pre_save, sender=Libro, dispatch_uid="libro_archivos_anteriores")
def guardar_archivos_anteriores(sender, instance, raw, **kwargs):
    instance._archivos_anteriores = {}
    if instance.pk and not raw:
        fila = sender.objects.filter(pk=instance.pk).values(*CAMPOS_ARCHIVO).first()
        instance._archivos_anteriores = fila or {}


@receiver(post_save, sender=Libro, dispatch_uid="libro_borrar_archivos_reemplazados")
def borrar_archivos_reemplazados(sender, instance, **kwargs):
    for campo, anterior in getattr(instance, "_archivos_anteriores", {}).items():
        archivo = getattr(instance, campo)
        if anterior and anterior != archivo.name:
            storage = archivo.storage
            # on_commit: si la transacción se deshace, el archivo antiguo sigue haciendo falta
            transaction.on_commit(lambda s=storage, n=anterior: s.delete(n))


@receiver(post_delete, sender=Libro, dispatch_uid="libro_borrar_archivos")
def borrar_archivos(sender, instance, **kwargs):
    for campo in CAMPOS_ARCHIVO:
        archivo = getattr(instance, campo)
        if archivo:
            transaction.on_commit(lambda s=archivo.storage, n=archivo.name: s.delete(n))


# ── módulo 23: cualquier cambio del catálogo invalida TODOS los listados cacheados ──
@receiver([post_save, post_delete], sender=Libro, dispatch_uid="libro_invalida_catalogo")
@receiver([post_save, post_delete], sender=Autor, dispatch_uid="autor_invalida_catalogo")
@receiver(m2m_changed, sender=Libro.autores.through, dispatch_uid="autoria_invalida_catalogo")
@receiver([post_save, post_delete], sender=Ejemplar, dispatch_uid="ejemplar_invalida_catalogo")
def invalidar_catalogo(sender, **kwargs):
    if kwargs.get("action", "post_").startswith("pre_"):  # m2m_changed avisa antes y después
        return
    transaction.on_commit(lambda: subir_version("catalogo"))
