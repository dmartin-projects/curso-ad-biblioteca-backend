from django.db import connection
from django.db.models import Count
from django.db.models.functions import TruncMonth

from .models import Prestamo


def resumen_mensual() -> list[dict]:
    """Préstamos por mes y acumulado, en SQL (CTE + window function sobre el agregado)."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            WITH por_mes AS (
                SELECT date_trunc('month', fecha_inicio) AS mes, COUNT(*) AS total
                FROM prestamos_prestamo
                GROUP BY 1
            )
            SELECT mes, total, SUM(total) OVER (ORDER BY mes) AS acumulado
            FROM por_mes ORDER BY mes
            """
        )
        columnas = [c.name for c in cursor.description]
        return [dict(zip(columnas, fila, strict=True)) for fila in cursor.fetchall()]


def resumen_mensual_orm() -> list[dict]:
    """Lo mismo con el ORM: agrega en la BD y acumula en Python (módulo 07, sección 10)."""
    filas = (
        Prestamo.objects.annotate(mes=TruncMonth("fecha_inicio"))
        .values("mes")
        .annotate(total=Count("id"))
        .order_by("mes")
    )
    acumulado = 0
    resultado = []
    for fila in filas:
        acumulado += fila["total"]
        resultado.append({**fila, "acumulado": acumulado})
    return resultado
