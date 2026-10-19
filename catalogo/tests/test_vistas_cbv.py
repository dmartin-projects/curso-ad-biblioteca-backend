import datetime as dt

import pytest

from catalogo.models import Autor, Libro

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def datos():
    le_guin = Autor.objects.create(nombre="Ursula K. Le Guin", slug="le-guin")
    herbert = Autor.objects.create(nombre="Frank Herbert", slug="herbert")
    dune = Libro.objects.create(titulo="Dune", isbn="9788497593793", publicado=dt.date(1965, 8, 1))
    dune.autores.add(herbert)
    desposeidos = Libro.objects.create(
        titulo="Los desposeídos", isbn="9788445076187", publicado=dt.date(1974, 5, 1)
    )
    desposeidos.autores.add(le_guin)


def test_lista_cbv_con_los_mismos_filtros(client):
    assert client.get("/catalogo/v2/libros/").json()["count"] == 2
    assert (
        client.get("/catalogo/v2/libros/?desde=1970").json()["results"][0]["titulo"]
        == "Los desposeídos"
    )
    assert client.get("/catalogo/v2/libros/?autor=herbert&q=du").json()["count"] == 1
    assert client.post("/catalogo/v2/libros/").status_code == 405  # BaseListView solo define get


def test_autor_cbv(client):
    r = client.get("/catalogo/v2/autores/le-guin/").json()
    assert r["nombre"] == "Ursula K. Le Guin" and r["libros"][0]["titulo"] == "Los desposeídos"
    assert client.get("/catalogo/v2/autores/nadie/").status_code == 404


def test_exportar_csv_filtrado(client):
    r = client.get("/catalogo/v2/libros/exportar/?autor=herbert")
    assert r["Content-Type"] == "text/csv; charset=utf-8"
    filas = r.content.decode().splitlines()
    assert filas == [
        "id,titulo,isbn,autores",
        f"{Libro.objects.get(titulo='Dune').pk},Dune,9788497593793,Frank Herbert",
    ]
