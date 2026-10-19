# prestamos/multas.py — la regla de multas, en un solo sitio (módulos 26 y 32)
from decimal import Decimal

MULTA_POR_DIA = Decimal("0.50")


def importe_multa(fecha_limite, momento) -> Decimal | None:
    """La usan devolver() y la tarea nocturna calcular_multas: siempre el mismo importe."""
    if momento <= fecha_limite:
        return None
    dias = max((momento - fecha_limite).days, 1)  # un retraso de horas ya cuenta como un día
    return dias * MULTA_POR_DIA
