# catalogo/tasks.py — importación en lotes paralelos con un chord (módulo 26)
from dataclasses import asdict

from celery import chord, shared_task
from django.utils import timezone

from .models import Importacion
from .servicios_importacion import importar_libros


@shared_task
def importar_lote(filas: list[dict]) -> dict:
    """Cada lote es todo-o-nada (módulo 19); devuelve un dict: los resultados viajan como JSON."""
    return asdict(importar_libros(filas))


@shared_task
def resumen_importacion(resultados: list[dict], importacion_id: int) -> dict:
    """El callback del chord: recibe la lista con lo que devolvió cada lote."""
    resumen = {
        "creados": sum(r["creados"] for r in resultados),
        "existentes": sum(r["existentes"] for r in resultados),
        "errores": [e for r in resultados for e in r["errores"]],
    }
    Importacion.objects.filter(pk=importacion_id).update(
        estado=Importacion.Estado.TERMINADA, terminada=timezone.now(), **resumen
    )
    return resumen


def lanzar_importacion(filas: list[dict], tam_lote: int = 100) -> Importacion:
    lotes = [filas[i : i + tam_lote] for i in range(0, len(filas), tam_lote)]
    importacion = Importacion.objects.create(lotes=len(lotes))
    chord(
        (importar_lote.s(lote) for lote in lotes),
        resumen_importacion.s(importacion.pk),
    ).apply_async()
    return importacion
