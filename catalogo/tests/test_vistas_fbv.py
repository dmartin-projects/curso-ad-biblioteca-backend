# catalogo/tests/test_vistas_fbv.py: comprobarlo (pytest, módulo 31; de momento: uv run pytest)
import datetime as dt

import pytest

from catalogo.models import Autor, Libro

pytestmark = pytest.mark.django_db


def test_filtros_y_detalle(client):
    le_guin = Autor.objects.create(nombre="Ursula K. Le Guin", slug="le-guin")
    herbert = Autor.objects.create(nombre="Frank Herbert", slug="herbert")
    Libro.objects.create(
        titulo="Dune", isbn="9788497593793", autor=herbert, publicado=dt.date(1965, 8, 1)
    )
    Libro.objects.create(
        titulo="Los desposeídos", isbn="9788445076187", autor=le_guin, publicado=dt.date(1974, 5, 1)
    )

    assert client.get("/catalogo/libros/").json()["count"] == 2
    assert client.get("/catalogo/libros/?desde=1970").json()["count"] == 1
    assert (
        client.get("/catalogo/libros/?desde=abc").json()["count"] == 2
    )  # un año inválido no rompe nada
    assert client.get("/catalogo/libros/?autor=herbert").json()["results"][0]["titulo"] == "Dune"
    assert client.post("/catalogo/libros/").status_code == 405  # require_GET
    assert len(client.get("/catalogo/autores/le-guin/").json()["libros"]) == 1
    assert client.get("/catalogo/autores/nadie/").status_code == 404


def test_detalle_libro_exige_permiso_para_cambiar_o_borrar(client, admin_client):
    herbert = Autor.objects.create(nombre="Frank Herbert", slug="herbert")
    libro = Libro.objects.create(titulo="Dune", isbn="9788497593793", autor=herbert)
    url = f"/catalogo/libros/{libro.pk}/"
    cambio = {"data": {"titulo": "Otro"}, "content_type": "application/json"}

    assert client.get(url).status_code == 200  # leer es público
    assert client.patch(url, **cambio).status_code == 403  # anónimo: ni cambia…
    assert client.delete(url).status_code == 403  # …ni borra
    assert Libro.objects.get(pk=libro.pk).titulo == "Dune"

    assert admin_client.patch(url, **cambio).json()["titulo"] == "Otro"  # con el permission, sí
    assert admin_client.delete(url).status_code == 204
    assert not Libro.objects.filter(pk=libro.pk).exists()


def test_health(client):
    assert client.get("/health/").json() == {"status": "ok"}
