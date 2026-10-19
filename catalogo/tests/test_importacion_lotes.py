"""Ejercicio del módulo 26 (4): chord que importa lotes en paralelo y guarda un resumen."""

import pytest

from catalogo.models import Importacion, Libro
from catalogo.tasks import lanzar_importacion

pytestmark = pytest.mark.django_db


def isbn13(n: int) -> str:
    """Genera un ISBN-13 válido (calcula el dígito de control)."""
    base = f"978{n:09d}"
    suma = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(base))
    return base + str((10 - suma % 10) % 10)


def filas(n: int, desde: int = 0) -> list[dict]:
    return [
        {"titulo": f"Libro {i}", "isbn": isbn13(i), "autor": f"Autor {i % 7}", "publicado": ""}
        for i in range(desde, desde + n)
    ]


def test_chord_importa_10_lotes_y_resume():
    Libro.objects.create(titulo="Ya estaba", isbn=isbn13(3))
    importacion = lanzar_importacion(filas(1000), tam_lote=100)  # 10 lotes

    importacion.refresh_from_db()
    assert importacion.lotes == 10
    assert importacion.estado == Importacion.Estado.TERMINADA
    assert (importacion.creados, importacion.existentes) == (999, 1)
    assert importacion.errores == []
    assert Libro.objects.count() == 1000


def test_un_lote_malo_no_tumba_los_demas():
    datos = filas(30)
    datos[15]["isbn"] = "9780000000000"  # dígito de control incorrecto (lote 2 de 3)
    importacion = lanzar_importacion(datos, tam_lote=10)
    importacion.refresh_from_db()
    assert importacion.creados == 20  # lotes 1 y 3; el 2, todo o nada
    assert len(importacion.errores) == 1 and "Fila 6" in importacion.errores[0]
