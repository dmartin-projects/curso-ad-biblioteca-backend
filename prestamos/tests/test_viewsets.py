"""Ejercicio del módulo 34: ViewSets, routers, @action y /auth/me/."""

from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

from catalogo.models import Libro
from catalogo.tests.factories import AutorFactory, EjemplarFactory, LibroFactory
from prestamos.models import Multa
from prestamos.tests.factories import PrestamoFactory
from usuarios.tests.factories import UsuarioFactory

pytestmark = pytest.mark.django_db


def cliente(usuario=None, grupo=None):
    if grupo:
        usuario.groups.add(Group.objects.get(name=grupo))
    api = APIClient()
    if usuario:
        api.force_authenticate(usuario)
    return api


# ── 1. LibroViewSet ──
def test_listado_y_detalle_usan_serializers_distintos(socio, django_assert_num_queries):
    for _ in range(5):
        EjemplarFactory.create_batch(2, libro=LibroFactory())
    api = cliente(socio)
    with django_assert_num_queries(3):  # libros (con la anotación) + autores + géneros
        lista = api.get("/api/v1/libros/").json()
    assert len(lista) == 5 and lista[0]["ejemplares_disponibles"] == 2
    detalle = api.get(f"/api/v1/libros/{lista[0]['id']}/").json()
    assert "ejemplares_disponibles" not in detalle and "sinopsis" in detalle
    assert isinstance(detalle["autores"][0], dict)  # anidado en el detalle


def test_socio_lee_pero_no_escribe(socio):
    api = cliente(socio)
    libro = LibroFactory()
    assert api.get(f"/api/v1/libros/{libro.pk}/").status_code == 200
    assert api.delete(f"/api/v1/libros/{libro.pk}/").status_code == 403
    assert api.patch(f"/api/v1/libros/{libro.pk}/", {"titulo": "X"}).status_code == 403


def test_bibliotecario_crea_y_edita_pero_no_borra():
    api = cliente(UsuarioFactory(), "bibliotecarios")
    autor = AutorFactory()
    r = api.post(
        "/api/v1/libros/",
        {"titulo": "Dune", "isbn": "978-0-441-17271-9", "autores_ids": [autor.pk]},
    )
    assert r.status_code == 201, r.json()
    pk = r.json()["id"]
    assert api.patch(f"/api/v1/libros/{pk}/", {"titulo": "Dune (2026)"}).json()["titulo"] == (
        "Dune (2026)"
    )
    assert api.delete(f"/api/v1/libros/{pk}/").status_code == 403  # su grupo no tiene delete_libro
    admin = cliente(UsuarioFactory(is_superuser=True))
    assert admin.delete(f"/api/v1/libros/{pk}/").status_code == 204


def test_borrar_libro_con_prestamos_es_409():
    prestamo = PrestamoFactory()
    api = cliente(UsuarioFactory(is_superuser=True))
    r = api.delete(f"/api/v1/libros/{prestamo.ejemplar.libro_id}/")
    assert r.status_code == 409
    assert Libro.objects.filter(pk=prestamo.ejemplar.libro_id).exists()


# ── 2. AutorViewSet por slug ──
def test_autor_por_slug():
    AutorFactory(nombre="Frank Herbert", slug="frank-herbert")
    assert (
        cliente(UsuarioFactory(), "bibliotecarios")
        .post(  # no tiene add_autor
            "/api/v1/autores/", {"nombre": "X"}
        )
        .status_code
        == 403
    )
    api = cliente(UsuarioFactory(is_superuser=True))
    assert api.get("/api/v1/autores/frank-herbert/").json()["nombre"] == "Frank Herbert"
    r = api.post("/api/v1/autores/", {"nombre": "Ursula K. Le Guin"})
    assert r.status_code == 201 and r.json()["slug"] == "ursula-k-le-guin"


# ── 3. PrestamoViewSet ──
def test_flujo_completo_de_un_prestamo(socio):
    api = cliente(socio)
    ejemplar = EjemplarFactory()
    r = api.post("/api/v1/prestamos/", {"ejemplar_id": ejemplar.pk})
    assert r.status_code == 201
    pk = r.json()["id"]

    limite = r.json()["fecha_limite"]
    r = api.post(f"/api/v1/prestamos/{pk}/renovar/")
    assert r.status_code == 200 and r.json()["fecha_limite"] > limite

    assert api.get("/api/v1/prestamos/").json()[0]["id"] == pk
    r = api.post(f"/api/v1/prestamos/{pk}/devolver/")
    assert r.json()["estado"] == "devuelto"
    assert api.post(f"/api/v1/prestamos/{pk}/devolver/").status_code == 409
    assert api.post(f"/api/v1/prestamos/{pk}/renovar/").status_code == 409


def test_no_hay_put_ni_delete(socio):
    prestamo = PrestamoFactory(socio=socio)
    api = cliente(socio)
    assert api.put(f"/api/v1/prestamos/{prestamo.pk}/", {}).status_code == 405
    assert api.delete(f"/api/v1/prestamos/{prestamo.pk}/").status_code == 405


def test_vencido_no_se_renueva_y_aparece_en_vencidos(socio):
    vencido = PrestamoFactory(socio=socio, vencido=True)
    PrestamoFactory(socio=socio)  # en plazo
    PrestamoFactory(vencido=True)  # de otro socio
    api = cliente(socio)
    assert api.post(f"/api/v1/prestamos/{vencido.pk}/renovar/").status_code == 409
    assert [p["id"] for p in api.get("/api/v1/prestamos/vencidos/").json()] == [vencido.pk]


def test_ajeno_da_404_y_el_bibliotecario_lo_ve_todo(socio):
    ajeno = PrestamoFactory()
    assert cliente(socio).get(f"/api/v1/prestamos/{ajeno.pk}/").status_code == 404
    assert cliente(socio).post(f"/api/v1/prestamos/{ajeno.pk}/devolver/").status_code == 404
    biblio = cliente(UsuarioFactory(), "bibliotecarios")
    assert len(biblio.get("/api/v1/prestamos/").json()) == 1


def test_listado_de_prestamos_sin_n_mas_1(socio, django_assert_num_queries):
    for prestamo in PrestamoFactory.create_batch(10, socio=socio, vencido=True)[:3]:
        Multa.objects.create(prestamo=prestamo, importe_base=Decimal("1.50"))
    api = cliente(socio)
    with django_assert_num_queries(3):  # grupos+permisos del usuario (has_perm) y préstamos
        assert len(api.get("/api/v1/prestamos/").json()) == 10


# ── 4. /auth/me/ ──
def test_me(socio):
    api = cliente(socio)
    assert api.get("/api/v1/auth/me/").json()["email"] == socio.email
    r = api.patch(
        "/api/v1/auth/me/", {"nombre": "Ana", "email": "otro@example.com", "idioma": "en"}
    )
    assert r.status_code == 200
    socio.refresh_from_db()
    assert (socio.nombre, socio.email, socio.idioma) == ("Ana", r.json()["email"], "en")
    assert socio.email != "otro@example.com"  # read_only: se ignora
    assert api.put("/api/v1/auth/me/", {"nombre": "X"}).status_code == 405
    assert cliente().get("/api/v1/auth/me/").status_code == 401  # 403 antes del módulo 35
