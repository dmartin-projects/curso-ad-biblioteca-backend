"""Ejercicio del módulo 19."""

from io import StringIO

import pytest
from django.contrib.postgres.search import SearchQuery
from django.core.management import CommandError, call_command
from django.utils import timezone

from catalogo.models import Ejemplar, Libro
from prestamos.models import Prestamo
from usuarios.models import Usuario

pytestmark = pytest.mark.django_db

CSV_BUENO = """titulo;isbn;autor;publicado
Dune;978-84-9759-379-3;Frank Herbert;1965-08-01
Los desposeídos;9788445076187;Ursula K. Le Guin;
"""


def test_importar_libros(tmp_path):
    ruta = tmp_path / "libros.csv"
    ruta.write_text(CSV_BUENO, encoding="utf-8")
    salida = StringIO()
    call_command("importar_libros", ruta, stdout=salida)
    assert "Creados: 2 · Ya existían: 0" in salida.getvalue()
    assert Libro.objects.get(isbn="9788497593793").autores.get().nombre == "Frank Herbert"
    call_command("importar_libros", ruta, stdout=salida)  # idempotente
    assert "Creados: 0 · Ya existían: 2" in salida.getvalue()


def test_dry_run_no_guarda(tmp_path):
    ruta = tmp_path / "libros.csv"
    ruta.write_text(CSV_BUENO, encoding="utf-8")
    salida = StringIO()
    call_command("importar_libros", ruta, dry_run=True, stdout=salida)
    assert "Dry run" in salida.getvalue() and "Creados: 2" in salida.getvalue()
    assert not Libro.objects.exists()


def test_una_fila_mala_y_no_se_importa_nada(tmp_path):
    ruta = tmp_path / "libros.csv"
    ruta.write_text(CSV_BUENO + "Malo;9788497593794;Nadie;\n", encoding="utf-8")
    errores = StringIO()
    with pytest.raises(CommandError, match="1 errores"):
        call_command("importar_libros", ruta, stderr=errores)
    assert "Fila 3, isbn: El dígito de control del ISBN no es válido." in errores.getvalue()
    assert not Libro.objects.exists()
    with pytest.raises(CommandError, match="No existe"):
        call_command("importar_libros", tmp_path / "no.csv")


def test_seed(settings):
    with pytest.raises(CommandError, match="solo se ejecuta en desarrollo"):
        call_command("seed")
    settings.DEBUG = True
    call_command("seed", libros=30, socios=5, prestamos=20, stdout=StringIO())
    assert Libro.objects.count() == 30 and Usuario.objects.count() == 5
    assert Prestamo.objects.count() == 20
    activos = Prestamo.objects.filter(estado="activo").count()
    assert Ejemplar.objects.filter(estado="prestado").count() == activos
    titulo = Libro.objects.first().titulo.split()[0]
    assert Libro.objects.filter(busqueda=SearchQuery(titulo, config="spanish")).exists()


def test_marcar_vencidos(settings):
    settings.DEBUG = True
    call_command("seed", libros=10, socios=2, prestamos=8, stdout=StringIO())
    vencidos = Prestamo.objects.filter(estado="activo", fecha_limite__lt=timezone.now()).count()
    salida = StringIO()
    call_command("marcar_vencidos", stdout=salida)
    assert f"{vencidos} préstamos vencidos avisados" in salida.getvalue()
