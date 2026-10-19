"""Ejercicio del módulo 33: serializers de catálogo y préstamos."""

from datetime import timedelta

import pytest
from django.contrib.postgres.search import SearchQuery
from django.utils import timezone
from rest_framework.test import APIClient

from catalogo.api.serializers import LibroListaSerializer, LibroSerializer
from catalogo.models import Autoria, Ejemplar, Genero, Libro
from catalogo.tests.factories import AutorFactory, EjemplarFactory, LibroFactory
from prestamos.models import Prestamo

pytestmark = pytest.mark.django_db
DUNE = "978-0-441-17271-9"  # con guiones: el serializer debe aceptarlo


@pytest.fixture
def herbert():
    return AutorFactory(nombre="Frank Herbert", slug="frank-herbert")


# ── 1 y 2. Libro: objeto para leer, ids para escribir; autorías con orden ──
def test_crear_libro_con_autores_en_orden(herbert):
    brian = AutorFactory(nombre="Brian Herbert", slug="brian-herbert")
    genero, _ = Genero.objects.get_or_create(nombre="Ciencia ficción")
    s = LibroSerializer(
        data={
            "titulo": "Dune",
            "isbn": DUNE,
            "autores_ids": [brian.pk, herbert.pk],
            "generos": [genero.pk],
        }
    )
    assert s.is_valid(), s.errors
    libro = s.save()

    assert libro.isbn == "9780441172719"  # normalizado
    orden = list(Autoria.objects.filter(libro=libro).values_list("autor__slug", "orden"))
    assert orden == [("brian-herbert", 0), ("frank-herbert", 1)]
    datos = LibroSerializer(libro).data
    assert [a["nombre"] for a in datos["autores"]] == ["Brian Herbert", "Frank Herbert"]
    assert "autores_ids" not in datos  # write_only
    assert datos["generos"] == [genero.pk]
    # bulk_create no emite m2m_changed: el servicio actualiza el vector de búsqueda a mano
    consulta = SearchQuery("herbert", config="spanish")
    assert list(Libro.objects.filter(busqueda=consulta)) == [libro]


def test_patch_sin_autores_no_los_toca(herbert):
    libro = LibroSerializer(data={"titulo": "Dune", "isbn": DUNE, "autores_ids": [herbert.pk]})
    libro.is_valid(raise_exception=True)
    libro = libro.save()
    s = LibroSerializer(libro, data={"titulo": "Dune (ed. 2026)"}, partial=True)
    s.is_valid(raise_exception=True)
    s.save()
    assert list(libro.autores.all()) == [herbert]


# ── 3 y 5. Validación ──
def test_autor_inexistente_es_400_en_su_campo(herbert):
    s = LibroSerializer(data={"titulo": "Dune", "isbn": DUNE, "autores_ids": [herbert.pk, 999]})
    assert not s.is_valid()
    assert list(s.errors) == ["autores_ids"]
    assert s.errors["autores_ids"][0].code == "does_not_exist"


@pytest.mark.parametrize(
    ("datos", "campo", "codigo"),
    [
        ({"isbn": "978-0-441-17271-8"}, "isbn", "isbn_control"),  # dígito de control mal
        ({"publicado": "2999-01-01"}, "publicado", "invalid"),
        ({"autores_ids": []}, "autores_ids", "invalid"),
    ],
)
def test_validaciones(herbert, datos, campo, codigo):
    base = {"titulo": "Dune", "isbn": DUNE, "autores_ids": [herbert.pk]}
    s = LibroSerializer(data={**base, **datos})
    assert not s.is_valid()
    assert s.errors[campo][0].code == codigo


def test_isbn_duplicado_con_o_sin_guiones(herbert):
    LibroFactory(isbn="9780441172719")
    s = LibroSerializer(data={"titulo": "Otra", "isbn": DUNE, "autores_ids": [herbert.pk]})
    assert not s.is_valid()  # el UniqueValidator compara el valor YA normalizado
    assert s.errors["isbn"][0].code == "unique"


# ── Listado: pocos campos y ejemplares_disponibles anotado, sin N+1 ──
def test_lista_con_disponibles_sin_n_mas_1(django_assert_num_queries):
    for _ in range(10):
        libro = LibroFactory()
        EjemplarFactory.create_batch(2, libro=libro)
        EjemplarFactory(libro=libro, estado=Ejemplar.Estado.PRESTADO)
    qs = Libro.objects.para_listado().con_disponibles().order_by("titulo")
    with django_assert_num_queries(3):  # libros + autores + géneros, tengas 10 o 1.000
        datos = LibroListaSerializer(qs, many=True).data
    assert len(datos) == 10 and {d["ejemplares_disponibles"] for d in datos} == {2}
    assert set(datos[0]) == {
        "id", "titulo", "isbn", "publicado", "autores", "generos", "ejemplares_disponibles",
    }  # fmt: skip


# ── 4. POST /api/v1/prestamos/ ──
@pytest.fixture
def api(socio):
    cliente = APIClient()
    cliente.force_authenticate(socio)
    return cliente


def test_prestar_por_api(api, socio):
    ejemplar = EjemplarFactory(libro__titulo="Dune")
    r = api.post("/api/v1/prestamos/", {"ejemplar_id": ejemplar.pk})
    assert r.status_code == 201
    datos = r.json()
    assert datos["libro"] == {
        "id": ejemplar.libro.pk,
        "titulo": "Dune",
        "isbn": ejemplar.libro.isbn,
    }
    assert datos["ejemplar"] == ejemplar.codigo and datos["estado"] == "activo"
    assert datos["fecha_inicio"] is not None  # la pone la BD (db_default)
    assert Prestamo.objects.get().socio == socio

    r = api.post("/api/v1/prestamos/", {"ejemplar_id": ejemplar.pk})
    assert r.status_code == 409


@pytest.mark.parametrize(
    ("cuerpo", "error"),
    [
        ({}, "ejemplar_id"),
        ({"ejemplar_id": 0}, "ejemplar_id"),
        ({"ejemplar_id": 999}, "ejemplar_id"),
    ],
)
def test_prestar_entrada_invalida(api, cuerpo, error):
    r = api.post("/api/v1/prestamos/", cuerpo)
    assert r.status_code == 400 and error in r.json()


def test_el_cliente_no_elige_socio_ni_fecha(api, socio):
    otro = AutorFactory()  # cualquier cosa: lo importante es que el campo se ignora
    ejemplar = EjemplarFactory()
    lejos = (timezone.now() + timedelta(days=365)).isoformat()
    r = api.post(
        "/api/v1/prestamos/", {"ejemplar_id": ejemplar.pk, "socio": otro.pk, "fecha_limite": lejos}
    )
    assert r.status_code == 201
    prestamo = Prestamo.objects.get()
    assert prestamo.socio == socio and prestamo.fecha_limite < timezone.now() + timedelta(days=30)
