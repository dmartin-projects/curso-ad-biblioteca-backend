"""Ejercicio del módulo 08: querysets, manager, lookup y SQL directo."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from catalogo.models import Autor, Ejemplar, Libro
from prestamos.consultas import resumen_mensual, resumen_mensual_orm
from prestamos.models import Prestamo
from usuarios.models import Usuario

pytestmark = pytest.mark.django_db
UTC = ZoneInfo("UTC")


@pytest.fixture
def biblioteca():
    herbert = Autor.objects.create(nombre="Frank Herbert", slug="herbert")
    dune = Libro.objects.create(titulo="Dune", isbn="9788497593793")
    dune.autores.add(herbert)
    hijos = Libro.objects.create(titulo="Hijos de Dune", isbn="9788497593809")
    hijos.autores.add(herbert)
    Ejemplar.objects.create(libro=dune, codigo="D1")
    Ejemplar.objects.create(libro=hijos, codigo="H1", estado="prestado")
    return dune, hijos


def test_libro_queryset_encadenable(biblioteca):
    dune, hijos = biblioteca
    assert list(Libro.objects.disponibles()) == [dune]
    assert Libro.objects.de_autor("herbert").count() == 2
    assert list(Libro.objects.disponibles().de_autor("herbert").buscar("dune")) == [dune]
    assert Libro.objects.buscar("HERBERT").count() == 2  # título o autor, sin duplicados
    herbert = Autor.objects.get(slug="herbert")
    assert list(herbert.libros.disponibles()) == [dune]  # también desde relaciones
    libro = Libro.objects.para_listado().get(pk=dune.pk)
    assert (libro.n_ejemplares, libro.n_prestamos) == (1, 0)


def test_prestamo_manager(biblioteca):
    dune, _ = biblioteca
    ana = Usuario.objects.create_user("ana@example.com")
    luis = Usuario.objects.create_user("luis@example.com")
    ejemplar = dune.ejemplares.get()
    ahora = timezone.now()
    vencido = Prestamo.objects.create(
        ejemplar=ejemplar,
        socio=ana,
        fecha_inicio=ahora - timedelta(days=30),
        fecha_limite=ahora - timedelta(days=9),
    )
    Prestamo.objects.filter(pk=vencido.pk).update(estado="devuelto", fecha_devolucion=ahora)
    en_plazo = Prestamo.objects.create(
        ejemplar=ejemplar, socio=luis, fecha_limite=ahora + timedelta(days=21)
    )
    assert list(Prestamo.objects.activos()) == [en_plazo]
    assert list(Prestamo.objects.vencidos()) == []
    # ahora el de ana sigue activo y fuera de plazo (y el de luis, devuelto)
    Prestamo.objects.filter(pk=en_plazo.pk).update(
        estado="devuelto", fecha_devolucion=timezone.now()
    )
    Prestamo.objects.filter(pk=vencido.pk).update(estado="activo", fecha_devolucion=None)
    assert list(Prestamo.objects.vencidos().de_socio(ana)) == [vencido]
    assert list(Prestamo.objects.vencidos().de_socio(luis)) == []
    # el manager ya trae libro y socio en la misma consulta
    with CaptureQueriesContext(connection) as consultas:
        p = Prestamo.objects.get(pk=vencido.pk)
        assert (p.ejemplar.libro.titulo, str(p.socio)) == ("Dune", "ana@example.com")
    assert len(consultas) == 1


def test_lookup_ne_y_transformacion(biblioteca):
    assert list(Libro.objects.filter(titulo__ne="Dune").values_list("titulo", flat=True)) == [
        "Hijos de Dune"
    ]
    assert Libro.objects.filter(titulo__longitud__gt=4).count() == 1


def test_resumen_mensual_sql_y_orm_coinciden(biblioteca):
    dune, _ = biblioteca
    ejemplar = dune.ejemplares.get()
    socio = Usuario.objects.create_user("ana@example.com")
    for mes, cantidad in [(1, 2), (2, 1), (4, 3)]:
        for _ in range(cantidad):
            inicio = datetime(2026, mes, 10, tzinfo=UTC)
            Prestamo.objects.create(
                ejemplar=ejemplar,
                socio=socio,
                fecha_inicio=inicio,
                fecha_limite=inicio + timedelta(days=21),
                estado="devuelto",
            )
    sql = resumen_mensual()
    assert [(f["mes"].month, f["total"], f["acumulado"]) for f in sql] == [
        (1, 2, 2),
        (2, 1, 3),
        (4, 3, 6),
    ]
    orm = resumen_mensual_orm()
    assert [(f["mes"].month, f["total"], f["acumulado"]) for f in orm] == [
        (1, 2, 2),
        (2, 1, 3),
        (4, 3, 6),
    ]
