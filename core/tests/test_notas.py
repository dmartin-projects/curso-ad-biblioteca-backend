"""Ejercicio del módulo 17."""

import json

import pytest
from django.db import connection
from django.db.models import Count
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from catalogo.models import Autor, Ejemplar, Libro
from core.models import Nota
from core.views import ultimas_notas
from prestamos.models import Prestamo
from usuarios.models import Usuario

pytestmark = pytest.mark.django_db


@pytest.fixture
def escena():
    ana = Usuario.objects.create_user("ana@example.com")
    luis = Usuario.objects.create_user("luis@example.com")
    libro = Libro.objects.create(titulo="Dune", isbn="9788497593793")
    autor = Autor.objects.create(nombre="Frank Herbert", slug="herbert")
    ejemplar = Ejemplar.objects.create(libro=libro, codigo="D1")
    de_luis = Prestamo.objects.create(ejemplar=ejemplar, socio=luis, fecha_limite=timezone.now())
    return {"ana": ana, "libro": libro, "autor": autor, "de_luis": de_luis}


def test_crear_y_listar_notas_de_cualquier_objeto(client, escena):
    client.force_login(escena["ana"])
    url = f"/notas/catalogo/libro/{escena['libro'].pk}/"
    r = client.post(url, json.dumps({"texto": "Portada rota"}), content_type="application/json")
    assert r.status_code == 201
    client.post(
        f"/notas/catalogo/autor/{escena['autor'].pk}/",
        json.dumps({"texto": "Biografía pendiente"}),
        content_type="application/json",
    )
    assert [n["texto"] for n in client.get(url).json()["results"]] == ["Portada rota"]
    # la relación inversa y el filtro por related_query_name
    assert escena["libro"].notas.count() == 1
    assert Libro.objects.filter(notas__texto__icontains="rota").get() == escena["libro"]
    assert Libro.objects.annotate(n=Count("notas")).get().n == 1


def test_validaciones_y_permisos(client, escena):
    assert client.get(f"/notas/catalogo/libro/{escena['libro'].pk}/").status_code == 302  # login
    client.force_login(escena["ana"])
    assert client.get("/notas/usuarios/usuario/1/").status_code == 404  # modelo no permitido
    assert client.get("/notas/catalogo/libro/999/").status_code == 404
    assert (
        client.get(f"/notas/prestamos/prestamo/{escena['de_luis'].pk}/").status_code == 404
    )  # ajeno
    r = client.post(
        f"/notas/catalogo/libro/{escena['libro'].pk}/", "{}", content_type="application/json"
    )
    assert r.status_code == 400


def test_borrar_el_libro_borra_sus_notas(escena):
    libro = Libro.objects.create(
        titulo="Fundación", isbn="9788497593809"
    )  # sin préstamos (PROTECT)
    Nota.objects.create(objeto=libro, usuario=escena["ana"], texto="x")
    Nota.objects.create(objeto=escena["autor"], usuario=escena["ana"], texto="y")
    libro.delete()
    assert list(Nota.objects.values_list("texto", flat=True)) == ["y"]  # gracias a GenericRelation


def test_ultimas_notas_sin_n_mas_1(escena):
    ana = escena["ana"]
    for i in range(10):
        Nota.objects.create(objeto=escena["libro"], usuario=ana, texto=f"l{i}")
        Nota.objects.create(objeto=escena["autor"], usuario=ana, texto=f"a{i}")
    with CaptureQueriesContext(connection) as consultas:
        resultado = ultimas_notas()
    assert len(resultado) == 20 and {r["tipo"] for r in resultado} == {"libro", "autor"}
    assert len(consultas) == 3  # notas + libros + autores, tengas 20 o 2.000 notas
