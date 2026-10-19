import json

import pytest

from catalogo.forms import BusquedaAvanzadaForm, FilasFormSet, a_datos_formset
from catalogo.models import Autor

pytestmark = pytest.mark.django_db


def test_busqueda_convierte_y_valida():
    form = BusquedaAvanzadaForm(data={"q": "  dune ", "desde": "1960", "hasta": "abc"})
    assert not form.is_valid()
    assert form.errors == {"hasta": ["Introduzca un número entero."]}
    assert form.cleaned_data == {"q": "dune", "desde": 1960, "solo_disponibles": False}
    form = BusquedaAvanzadaForm(data={"desde": "2000", "hasta": "1990"})
    assert not form.is_valid() and "hasta" in form.errors


def test_crear_libro_por_json(admin_client):  # la view exige catalogo.add_libro
    autor = Autor.objects.create(nombre="Frank Herbert", slug="herbert")
    malo = {"titulo": "Dune", "isbn": "9788497593794", "autor": autor.pk}
    r = admin_client.post(
        "/catalogo/libros/nuevo/", json.dumps(malo), content_type="application/json"
    )
    assert r.status_code == 400
    assert r.json() == {
        "errores": {
            "isbn": [
                {"message": "El dígito de control del ISBN no es válido.", "code": "isbn_control"}
            ]
        }
    }
    bueno = {**malo, "isbn": "9788497593793", "titulo": "  Dune "}
    r = admin_client.post(
        "/catalogo/libros/nuevo/", json.dumps(bueno), content_type="application/json"
    )
    assert r.status_code == 201 and r.json()["titulo"] == "Dune"
    r = admin_client.post(
        "/catalogo/libros/nuevo/", json.dumps(bueno), content_type="application/json"
    )
    assert r.json()["errores"]["isbn"][0]["message"] == "Ya existe un libro con ese ISBN."


def test_formset_rechaza_isbn_repetido():
    filas = [
        {"isbn": "9788497593793", "titulo": "Dune", "autor": "Herbert"},
        {"isbn": "9788497593793", "titulo": "Dune bis", "autor": "Herbert"},
    ]
    formset = FilasFormSet(data=a_datos_formset(filas))
    assert not formset.is_valid()
    assert formset.non_form_errors() == ["ISBN repetido en el archivo: 9788497593793"]
    filas[1]["isbn"] = "97884"
    formset = FilasFormSet(data=a_datos_formset(filas))
    assert not formset.is_valid() and formset.errors[1] == {
        "isbn": ["El ISBN debe tener 13 dígitos."]
    }
