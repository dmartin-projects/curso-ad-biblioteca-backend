# catalogo/tasks.py — importación en lotes paralelos con un chord (módulo 26)
import logging
from dataclasses import asdict
from datetime import date

from celery import chord, shared_task
from django.utils import timezone

from core.circuit_breaker import CircuitBreaker, CircuitoAbierto

from .clients.openlibrary import OpenLibraryClient, OpenLibraryError
from .models import Importacion, Libro
from .servicios_importacion import importar_libros

logger = logging.getLogger(__name__)


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


# ── módulo 27: completar datos desde Open Library ──
breaker_openlibrary = CircuitBreaker("openlibrary", umbral=5, enfriamiento=120)


@shared_task(bind=True, rate_limit="60/m", max_retries=5)  # límite de uso en origen
def completar_desde_openlibrary(self, libro_id: int) -> str:
    libro = Libro.objects.get(pk=libro_id)
    logger.info("Completando libro %s (ISBN %s) desde Open Library", libro_id, libro.isbn)
    try:
        datos = breaker_openlibrary.llamar(OpenLibraryClient().buscar_isbn, libro.isbn)
    except CircuitoAbierto as exc:
        raise self.retry(exc=exc, countdown=120) from exc  # cuando el circuito se enfríe
    except OpenLibraryError as exc:
        raise self.retry(exc=exc, countdown=60) from exc
    if datos is None:
        return "no encontrado"

    cambios = []
    if libro.paginas is None and datos.paginas:  # solo rellena huecos: no pisa lo editado a mano
        libro.paginas = datos.paginas
        cambios.append("paginas")
    if libro.publicado is None and datos.anio:
        libro.publicado = date(datos.anio, 1, 1)
        cambios.append("publicado")
    libro.metadatos = {**libro.metadatos, "openlibrary": {"autores": datos.autores}}
    libro.save(update_fields=[*cambios, "metadatos"])
    return f"actualizado: {', '.join(cambios) or 'nada'}"
