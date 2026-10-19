"""Ejercicio del módulo 10: la migración de datos y el fixture con claves naturales."""

import pytest
from django.core.management import call_command

from catalogo.models import Genero

pytestmark = pytest.mark.django_db


def test_la_migracion_crea_los_generos_basicos():
    # la BD de test se crea aplicando TODAS las migraciones, también las de datos
    assert Genero.objects.get(nombre="Ciencia ficción").padre.nombre == "Novela"
    assert Genero.objects.count() == 5


def test_fixture_con_claves_naturales_en_bd_vacia():
    Genero.objects.filter(padre__isnull=False).delete()
    Genero.objects.all().delete()
    call_command("loaddata", "generos", verbosity=0)  # busca catalogo/fixtures/generos.json
    hija = Genero.objects.get(nombre="Ciencia ficción")
    assert hija.padre == Genero.objects.get(
        nombre="Novela"
    )  # el padre se resuelve por nombre, no por pk
