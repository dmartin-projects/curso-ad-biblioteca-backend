"""Ejercicio del módulo 11."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from catalogo.models import Autor, Libro
from prestamos.models import ReservaSala, Sala
from usuarios.models import Usuario

pytestmark = pytest.mark.django_db


@pytest.fixture
def libros():
    dune = Libro.objects.create(
        titulo="Dune",
        isbn="9788497593793",
        sinopsis="Una saga de viajes espaciales, política y religión en el planeta desierto Arrakis.",
        metadatos={"editorial": "Debolsillo", "formatos": ["tapa blanda", "ebook"]},
        etiquetas=["clásico", "saga"],
    )
    fundacion = Libro.objects.create(
        titulo="Fundación",
        isbn="9788497593809",
        sinopsis="La caída de un imperio galáctico y un plan para acortar la edad oscura.",
        metadatos={"editorial": "Debolsillo"},
        etiquetas=["clásico"],
    )
    hobbit = Libro.objects.create(
        titulo="El hobbit",
        isbn="9788445073728",
        sinopsis="Un viaje inesperado con trece enanos y un dragón.",
        metadatos={"editorial": "Minotauro"},
    )
    return dune, fundacion, hobbit


def test_json_y_array(libros):
    dune, fundacion, _ = libros
    assert set(Libro.objects.filter(metadatos__editorial="Debolsillo")) == {dune, fundacion}
    assert list(Libro.objects.filter(metadatos__formatos__contains=["ebook"])) == [dune]
    assert set(Libro.objects.filter(etiquetas__contains=["clásico"])) == {dune, fundacion}
    assert list(Libro.objects.filter(etiquetas__len__gt=1)) == [dune]


def test_busqueda_por_relevancia(client, libros):
    # "viaje" encuentra "viajes" (raíz en español); el título (peso A) pesa más que la sinopsis (B)
    r = client.get("/catalogo/libros/buscar/", {"q": "viaje"}).json()["results"]
    assert {x["titulo"] for x in r} == {"Dune", "El hobbit"}
    assert "<b>" in r[0]["fragmento"]  # SearchHeadline resalta las palabras encontradas
    r = client.get("/catalogo/libros/buscar/", {"q": "dune -hobbit"}).json()["results"]
    assert [x["titulo"] for x in r] == ["Dune"]
    # el vector se mantiene al editar
    libros[2].titulo = "El hobbit: un viaje inesperado"
    libros[2].save()
    r = client.get("/catalogo/libros/buscar/", {"q": "inesperado"}).json()["results"]
    assert r[0]["titulo"] == "El hobbit: un viaje inesperado"


def test_autocompletar_tolera_erratas_y_acentos(client):
    Autor.objects.create(nombre="Gabriel García Márquez", slug="garcia-marquez")
    Autor.objects.create(nombre="Frank Herbert", slug="herbert")

    def nombres(q):
        r = client.get("/catalogo/autores/autocompletar/", {"q": q}).json()["results"]
        return [a["nombre"] for a in r]

    assert nombres("herbet") == ["Frank Herbert"]  # errata
    assert nombres("garcia") == ["Gabriel García Márquez"]  # sin acento
    assert nombres("marqes") == ["Gabriel García Márquez"]  # sin acento y con errata
    assert nombres("x") == []


def test_reservas_solapadas_de_la_misma_sala():
    sala, otra = Sala.objects.create(nombre="Estudio 1"), Sala.objects.create(nombre="Estudio 2")
    socio = Usuario.objects.create_user("ana")
    t = datetime(2026, 11, 3, 10, tzinfo=ZoneInfo("Europe/Madrid"))
    ReservaSala.objects.create(sala=sala, socio=socio, periodo=(t, t + timedelta(hours=2)))
    # otra sala a la misma hora, o la misma sala justo después: sin problema
    ReservaSala.objects.create(sala=otra, socio=socio, periodo=(t, t + timedelta(hours=2)))
    ReservaSala.objects.create(
        sala=sala, socio=socio, periodo=(t + timedelta(hours=2), t + timedelta(hours=3))
    )
    solapada = ReservaSala(
        sala=sala, socio=socio, periodo=(t + timedelta(hours=1), t + timedelta(hours=4))
    )
    with pytest.raises(ValidationError, match="La sala ya está reservada"):
        solapada.full_clean()  # lo que haría un formulario o el admin
    with pytest.raises(IntegrityError, match="sin_solapamiento_por_sala"), transaction.atomic():
        solapada.save()  # y la BD, aunque nadie valide
