"""Ejercicio del módulo 07: las siete consultas, con datos conocidos."""

from datetime import timedelta

import pytest
from django.db.models import (
    Count,
    DurationField,
    Exists,
    ExpressionWrapper,
    F,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Window,
)
from django.db.models.functions import Rank, RowNumber
from django.utils import timezone

from catalogo.models import Autor, Ejemplar, Genero, Libro
from prestamos.models import Prestamo
from usuarios.models import Usuario

pytestmark = pytest.mark.django_db


@pytest.fixture
def datos():
    ahora = timezone.now()
    le_guin = Autor.objects.create(nombre="Ursula K. Le Guin", slug="le-guin")
    herbert = Autor.objects.create(nombre="Frank Herbert", slug="herbert")
    tolkien = Autor.objects.create(nombre="J. R. R. Tolkien", slug="tolkien")
    sf, fantasia = (
        # "Ciencia ficción" ya existe: la crea la migración de datos del módulo 10
        Genero.objects.get_or_create(nombre="Ciencia ficción")[0],
        Genero.objects.create(nombre="Fantasía"),
    )
    dune = Libro.objects.create(titulo="Dune", isbn="9788497593793")
    dune.autores.add(herbert)
    dune.generos.add(sf)
    terramar = Libro.objects.create(titulo="Un mago de Terramar", isbn="9788445076187")
    terramar.autores.add(le_guin)
    terramar.generos.add(fantasia, sf)
    hobbit = Libro.objects.create(titulo="El hobbit", isbn="9788445073728")  # "le" no está
    hobbit.autores.add(tolkien)
    hobbit.generos.add(fantasia)
    ana, luis = (
        Usuario.objects.create_user("ana@example.com"),
        Usuario.objects.create_user("luis@example.com"),
    )
    ejemplares = {
        "D1": Ejemplar.objects.create(libro=dune, codigo="D1"),
        "D2": Ejemplar.objects.create(libro=dune, codigo="D2"),
        "D3": Ejemplar.objects.create(libro=dune, codigo="D3", estado="prestado"),
        "T1": Ejemplar.objects.create(libro=terramar, codigo="T1", estado="prestado"),
        "H1": Ejemplar.objects.create(libro=hobbit, codigo="H1", estado="prestado"),
    }

    def prestar(socio, codigo, dias_atras, activo=True, devuelto_dias_tarde=None):
        inicio = ahora - timedelta(days=dias_atras)
        p = Prestamo.objects.create(
            ejemplar=ejemplares[codigo],
            socio=socio,
            fecha_inicio=inicio,
            fecha_limite=inicio + timedelta(days=21),
            estado="activo" if activo else "devuelto",
        )
        if devuelto_dias_tarde is not None:
            p.fecha_devolucion = p.fecha_limite + timedelta(days=devuelto_dias_tarde)
            p.save()
        return p

    # ana: 3 activos; luis: 1 activo y 2 devueltos (uno tarde)
    prestar(ana, "D3", 2)
    prestar(ana, "T1", 3)
    prestar(ana, "H1", 4)
    prestar(luis, "D1", 1)
    prestar(luis, "D2", 60, activo=False, devuelto_dias_tarde=5)
    prestar(luis, "D2", 30, activo=False, devuelto_dias_tarde=-2)
    return locals()


def test_1_titulo_o_autor_con_le(datos):
    qs = Libro.objects.filter(
        Q(titulo__icontains="le") | Q(autores__nombre__icontains="le")
    ).distinct()
    assert set(qs.values_list("titulo", flat=True)) == {"Un mago de Terramar"}  # Le Guin


def test_2_libros_por_genero(datos):
    qs = Genero.objects.annotate(n=Count("libros")).order_by("-n", "nombre")
    assert [(g.nombre, g.n) for g in qs[:2]] == [("Ciencia ficción", 2), ("Fantasía", 2)]


def test_3_socios_con_mas_de_2_activos(datos):
    qs = Usuario.objects.annotate(activos=Count("prestamos", filter=Q(prestamos__estado="activo")))
    assert list(qs.filter(activos__gt=2).values_list("pk", flat=True)) == [datos["ana"].pk]


def test_4_ejemplares_prestamos_disponible(datos):
    disponible = Ejemplar.objects.filter(libro=OuterRef("pk"), estado="disponible")
    qs = Libro.objects.annotate(
        n_ejemplares=Count("ejemplares", distinct=True),
        n_prestamos=Count("ejemplares__prestamos", distinct=True),
        hay_disponible=Exists(disponible),
    )
    dune = qs.get(titulo="Dune")
    assert (dune.n_ejemplares, dune.n_prestamos, dune.hay_disponible) == (3, 4, True)
    assert qs.get(titulo="El hobbit").hay_disponible is False


def test_5_devueltos_con_retraso(datos):
    qs = Prestamo.objects.filter(fecha_devolucion__gt=F("fecha_limite")).annotate(
        retraso=ExpressionWrapper(
            F("fecha_devolucion") - F("fecha_limite"), output_field=DurationField()
        ),
    )
    assert [p.retraso.days for p in qs] == [5]


def test_6_ranking_de_autores(datos):
    qs = (
        Autor.objects.annotate(n=Count("libros__ejemplares__prestamos"))
        .annotate(posicion=Window(Rank(), order_by=F("n").desc()))
        .order_by("posicion", "nombre")
    )
    assert [(a.slug, a.n, a.posicion) for a in qs] == [
        ("herbert", 4, 1),
        ("tolkien", 1, 2),
        ("le-guin", 1, 2),
    ]


def test_7_ultimo_prestamo_de_cada_socio(datos):
    qs = Prestamo.objects.annotate(
        orden=Window(RowNumber(), partition_by=F("socio"), order_by=F("fecha_inicio").desc()),
    ).filter(orden=1)
    assert {(str(p.socio), p.ejemplar.codigo) for p in qs} == {
        ("ana@example.com", "D3"),
        ("luis@example.com", "D1"),
    }


def test_subquery_count_de_la_seccion_8(datos):
    class SubqueryCount(Subquery):
        template = "(SELECT COUNT(*) FROM (%(subquery)s) _cuenta)"
        output_field = IntegerField()

    qs = Autor.objects.annotate(
        n_libros=SubqueryCount(Libro.objects.filter(autores=OuterRef("pk")).values("pk")),
    )
    assert {a.slug: a.n_libros for a in qs} == {"herbert": 1, "le-guin": 1, "tolkien": 1}
