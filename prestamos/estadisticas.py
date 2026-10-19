# prestamos/estadisticas.py — estadísticas cacheadas (módulo 23)
from django.core.cache import cache
from django.db.models import Count
from django.db.models.functions import TruncMonth

from .models import Prestamo

CLAVE_ESTADISTICAS = "estadisticas:prestamos"


def estadisticas_prestamos() -> dict:
    return cache.get_or_set(CLAVE_ESTADISTICAS, _calcular_estadisticas, timeout=600)


def _calcular_estadisticas() -> dict:
    por_mes = (
        Prestamo.objects.annotate(mes=TruncMonth("fecha_inicio"))
        .values("mes")
        .annotate(total=Count("id"))
        .order_by("mes")
    )
    return {
        "activos": Prestamo.objects.activos().count(),
        "vencidos": Prestamo.objects.vencidos().count(),
        "por_mes": [{"mes": f["mes"].date().isoformat(), "total": f["total"]} for f in por_mes],
    }


def invalidar_estadisticas() -> None:
    cache.delete(CLAVE_ESTADISTICAS)
