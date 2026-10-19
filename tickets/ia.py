# tickets/ia.py — el "proveedor de IA" (en el proyecto final, una llamada a una API real)
import re
from decimal import Decimal


class ErrorIA(ConnectionError):
    """Error transitorio del proveedor (red, 5xx, 429): reintentar tiene sentido."""


def extraer_con_ia(texto: str) -> dict:
    """Simulación: 'MERCADONA ... TOTAL 23,45' → {'comercio': 'MERCADONA', 'importe': 23.45}."""
    total = re.search(r"TOTAL\s+(\d+[.,]\d{2})", texto)
    if not total:
        raise ValueError("No se encuentra el total")  # error de datos: reintentar no lo arregla
    return {
        "comercio": texto.split()[0],
        "importe": Decimal(total.group(1).replace(",", ".")),
    }
