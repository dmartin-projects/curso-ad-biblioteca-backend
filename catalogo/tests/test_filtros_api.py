"""Ejercicio del módulo 37: filtros, búsqueda, ordenación y paginación."""

from datetime import date, timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from catalogo.models import Ejemplar, Genero
from catalogo.tests.factories import AutorFactory, EjemplarFactory, LibroFactory
from prestamos.tests.factories import PrestamoFactory
from usuarios.tests.factories import UsuarioFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def api(socio):
    cliente = APIClient()
    cliente.force_authenticate(socio)
    return cliente


def titulos(r):
    assert r.status_code == 200, r.json()
    return [libro["titulo"] for libro in r.json()["results"]]


@pytest.fixture
def catalogo():
    herbert = AutorFactory(nombre="Frank Herbert", slug="frank-herbert")
    garcia = AutorFactory(nombre="Gabriel García Márquez", slug="garcia-marquez")
    scifi, _ = Genero.objects.get_or_create(nombre="Ciencia ficción")
    novela, _ = Genero.objects.get_or_create(nombre="Novela")
    dune = LibroFactory(titulo="Dune", autores=[herbert], publicado=date(1965, 8, 1), paginas=600)
    dune.generos.set([scifi, novela])  # dos géneros: tentación de duplicados
    cien = LibroFactory(
        titulo="Cien años de soledad", autores=[garcia], publicado=date(1967, 5, 30), paginas=471
    )
    cien.generos.set([novela])
    hijos = LibroFactory(
        titulo="Hijos de Dune", autores=[herbert], publicado=date(1976, 1, 1), paginas=420
    )
    EjemplarFactory(libro=dune)
    EjemplarFactory(libro=cien, estado=Ejemplar.Estado.PRESTADO)
    return {"scifi": scifi, "novela": novela, "dune": dune, "cien": cien, "hijos": hijos}


# ── 1. LibroFilter ──
def test_filtros_de_libros(api, catalogo):
    g = catalogo
    assert titulos(api.get("/api/v1/libros/", {"titulo": "dune"})) == ["Dune", "Hijos de Dune"]
    assert titulos(api.get("/api/v1/libros/", {"autor": "garcia-marquez"})) == [
        "Cien años de soledad"
    ]
    r = api.get("/api/v1/libros/", {"genero": [g["scifi"].pk, g["novela"].pk]})  # OR
    assert titulos(r) == ["Cien años de soledad", "Dune"]  # Dune una vez aunque tenga los dos
    r = api.get(
        "/api/v1/libros/", {"publicado_desde": "1966-01-01", "publicado_hasta": "1970-12-31"}
    )
    assert titulos(r) == ["Cien años de soledad"]
    assert titulos(api.get("/api/v1/libros/", {"paginas_min": 450, "paginas_max": 500})) == [
        "Cien años de soledad"
    ]
    assert titulos(api.get("/api/v1/libros/", {"disponible": "true"})) == ["Dune"]
    assert titulos(api.get("/api/v1/libros/", {"disponible": "false"})) == [
        "Cien años de soledad",
        "Hijos de Dune",
    ]


def test_filtro_invalido_es_400(api, catalogo):
    r = api.get("/api/v1/libros/", {"publicado_desde": "ayer"})
    assert r.status_code == 400 and "publicado_desde" in r.json()["errors"]  # formato del 38
    r = api.get("/api/v1/libros/", {"genero": 9999})
    assert r.status_code == 400 and "genero" in r.json()["errors"]


# ── 2. Búsqueda ──
def test_busqueda(api, catalogo):
    assert titulos(api.get("/api/v1/libros/", {"search": "herbert hijos"})) == ["Hijos de Dune"]
    isbn = catalogo["dune"].isbn
    assert titulos(api.get("/api/v1/libros/", {"search": isbn})) == ["Dune"]  # =isbn: exacto
    assert titulos(api.get("/api/v1/libros/", {"search": isbn[:6]})) == []  # parcial: nada


def test_busqueda_de_autores_sin_acentos(api, catalogo):
    r = api.get("/api/v1/autores/", {"search": "garcia marquez"})
    assert [a["nombre"] for a in r.json()["results"]] == ["Gabriel García Márquez"]


# ── Ordenación ──
def test_ordenacion_y_lista_blanca(api, catalogo):
    r = api.get("/api/v1/libros/", {"ordering": "-publicado"})
    assert titulos(r) == ["Hijos de Dune", "Cien años de soledad", "Dune"]
    r = api.get("/api/v1/libros/", {"ordering": "-ejemplares_disponibles,titulo"})
    assert titulos(r)[0] == "Dune"
    r = api.get("/api/v1/libros/", {"ordering": "-sinopsis"})  # no está en ordering_fields
    assert titulos(r) == [
        "Cien años de soledad",
        "Dune",
        "Hijos de Dune",
    ]  # se ignora: el de defecto


# ── 3. Paginación ──
def test_paginacion_estandar_con_maximo(api):
    LibroFactory.create_batch(120)
    r = api.get("/api/v1/libros/", {"page_size": 1000}).json()
    assert len(r["results"]) == 100  # max_page_size
    assert (r["count"], r["total_pages"], r["page"], r["page_size"]) == (120, 2, 1, 100)
    r = api.get("/api/v1/libros/", {"page": 2}).json()
    assert (len(r["results"]), r["total_pages"], r["previous"] is not None) == (20, 6, True)
    assert api.get("/api/v1/libros/", {"page": 99}).status_code == 404


def test_generos_sin_paginar(api):
    assert isinstance(api.get("/api/v1/generos/").json(), list)


# ── 4. Cursor en el historial de préstamos ──
def test_cursor_estable_aunque_entren_prestamos(socio):
    api = APIClient()
    api.force_authenticate(socio)
    ahora = timezone.now()
    for i in range(25):
        p = PrestamoFactory(socio=socio)
        type(p).objects.filter(pk=p.pk).update(fecha_inicio=ahora - timedelta(days=i))
    primera = api.get("/api/v1/prestamos/").json()
    assert len(primera["results"]) == 20 and "count" not in primera  # sin COUNT(*)

    PrestamoFactory(socio=socio)  # llega uno nuevo mientras hace scroll
    segunda = api.get(primera["next"]).json()
    ids = [p["id"] for p in primera["results"] + segunda["results"]]
    assert len(ids) == 25 == len(set(ids))  # ni repetidos ni saltados
    assert segunda["next"] is None


def test_cursor_con_empates_en_el_primer_campo_es_un_offset(socio):
    """El cursor solo filtra por el primer campo de ordering; los empates se saltan con offset."""
    api = APIClient()
    api.force_authenticate(socio)
    mismo_instante = timezone.now() - timedelta(days=1)
    for _ in range(25):
        p = PrestamoFactory(socio=socio)
        type(p).objects.filter(pk=p.pk).update(fecha_inicio=mismo_instante)
    primera = api.get("/api/v1/prestamos/").json()

    nuevo = PrestamoFactory(socio=socio)  # mismo instante e id mayor: se ordena el primero
    type(nuevo).objects.filter(pk=nuevo.pk).update(fecha_inicio=mismo_instante)
    segunda = api.get(primera["next"]).json()
    ids = [p["id"] for p in primera["results"] + segunda["results"]]
    assert len(ids) == 26 and len(set(ids)) == 25  # uno repetido: con empates, es OFFSET 20


# ── 5. Un socio no puede nombrar a otro socio en un filtro ──
def test_filtro_por_socio_ajeno_es_400(socio):
    otro = UsuarioFactory()
    PrestamoFactory(socio=otro)
    api = APIClient()
    api.force_authenticate(socio)
    r = api.get("/api/v1/prestamos/", {"socio": otro.pk})
    assert r.status_code == 400 and "socio" in r.json()["errors"]  # ni confirma que existe
    assert api.get("/api/v1/prestamos/", {"socio": socio.pk}).status_code == 200
