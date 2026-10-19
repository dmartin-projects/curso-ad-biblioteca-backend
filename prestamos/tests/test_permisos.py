"""Ejercicio del módulo 14."""

import pytest
from django.contrib.auth.models import Group
from django.utils import timezone

from catalogo.models import Ejemplar, Libro
from prestamos.models import Prestamo
from usuarios.models import Usuario

pytestmark = pytest.mark.django_db


@pytest.fixture
def escena():
    libro = Libro.objects.create(titulo="Dune", isbn="9788497593793")
    ana = Usuario.objects.create_user("ana@example.com")
    luis = Usuario.objects.create_user("luis@example.com")
    biblio = Usuario.objects.create_user("biblio@example.com")
    ana.groups.add(Group.objects.get(name="socios"))
    luis.groups.add(Group.objects.get(name="socios"))
    biblio.groups.add(Group.objects.get(name="bibliotecarios"))

    def prestamo(socio, codigo):
        e = Ejemplar.objects.create(libro=libro, codigo=codigo)
        return Prestamo.objects.create(
            ejemplar=e, socio=socio, fecha_limite=timezone.now() + Prestamo.DURACION
        )

    return {
        "ana": ana,
        "luis": luis,
        "biblio": biblio,
        "de_ana": prestamo(ana, "E1"),
        "de_luis": prestamo(luis, "E2"),
    }


def test_los_grupos_existen_con_sus_permisos(escena):
    assert escena["biblio"].has_perm("prestamos.renovar_prestamo")
    assert not escena["ana"].has_perm("prestamos.renovar_prestamo")  # global, no
    assert escena["ana"].has_perm("prestamos.renovar_prestamo", escena["de_ana"])  # el suyo, sí
    assert not escena["ana"].has_perm("prestamos.renovar_prestamo", escena["de_luis"])
    responsables = Group.objects.get(name="responsables")
    assert responsables.permissions.filter(codename="renovar_prestamo").exists()  # heredado


def test_renovar_segun_rol(client, escena):
    url = lambda p: f"/prestamos/{p.pk}/renovar/"  # noqa: E731
    client.force_login(escena["ana"])
    assert client.post(url(escena["de_ana"])).status_code == 200
    assert client.post(url(escena["de_luis"])).status_code == 403
    assert client.get(url(escena["de_ana"])).status_code == 405  # solo POST
    client.force_login(escena["biblio"])
    assert client.post(url(escena["de_luis"])).status_code == 200
    escena["de_luis"].estado = "devuelto"
    escena["de_luis"].fecha_devolucion = timezone.now()
    escena["de_luis"].save()
    assert client.post(url(escena["de_luis"])).status_code == 409


def test_mis_prestamos_y_404_para_ajenos(client, escena):
    assert client.get("/prestamos/").status_code == 403  # sin login (raise_exception)
    client.force_login(escena["ana"])
    ids = [p["id"] for p in client.get("/prestamos/").json()["results"]]
    assert ids == [escena["de_ana"].pk]
    assert client.get(f"/prestamos/{escena['de_ana'].pk}/").status_code == 200
    assert (
        client.get(f"/prestamos/{escena['de_luis'].pk}/").status_code == 404
    )  # ni se sabe que existe
    client.force_login(escena["biblio"])
    assert len(client.get("/prestamos/").json()["results"]) == 2
