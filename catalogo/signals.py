from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver

from .busqueda import actualizar_busqueda
from .models import Autor, Libro


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
