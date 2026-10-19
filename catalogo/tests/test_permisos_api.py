"""Ejercicio del módulo 36: matriz de permisos, permisos de modelo y throttling."""

import pytest
from django.contrib.auth.models import Group, Permission
from rest_framework.test import APIClient

from catalogo.models import Genero
from catalogo.tests.factories import AutorFactory, LibroFactory
from prestamos.tests.factories import PrestamoFactory
from usuarios.tests.factories import UsuarioFactory

pytestmark = pytest.mark.django_db


def como(rol: str, socio_del_prestamo=None) -> APIClient:
    api = APIClient()
    if rol == "anonimo":
        return api
    if rol == "socio":
        usuario = socio_del_prestamo
    else:
        usuario = UsuarioFactory()
        if rol == "bibliotecario":
            usuario.groups.add(Group.objects.get(name="bibliotecarios"))
    api.force_authenticate(usuario)
    return api


ROLES = ["anonimo", "socio", "otro_socio", "bibliotecario"]


# ── 5. Matriz de libros: listar, ver, crear, editar, borrar ──
LIBROS = {  # rol: (listar, ver, crear, editar, borrar)
    "anonimo": (401, 401, 401, 401, 401),
    "socio": (200, 200, 403, 403, 403),
    "otro_socio": (200, 200, 403, 403, 403),
    "bibliotecario": (200, 200, 201, 200, 204),
}


@pytest.mark.parametrize("rol", ROLES)
def test_matriz_libros(rol):
    socio = UsuarioFactory()
    api = como(rol, socio)
    libro = LibroFactory()
    autor = AutorFactory()
    nuevo = {"titulo": "Nuevo", "isbn": "9788498003253", "autores_ids": [autor.pk]}
    obtenidos = (
        api.get("/api/v1/libros/").status_code,
        api.get(f"/api/v1/libros/{libro.pk}/").status_code,
        api.post("/api/v1/libros/", nuevo).status_code,
        api.patch(f"/api/v1/libros/{libro.pk}/", {"titulo": "X"}).status_code,
        api.delete(f"/api/v1/libros/{libro.pk}/").status_code,
    )
    assert obtenidos == LIBROS[rol]


# ── 5. Matriz de préstamos (de un socio concreto) ──
PRESTAMOS = {  # rol: (listar → nº visibles, ver, devolver, vencidos)
    "anonimo": (401, 401, 401, 401),
    "socio": (1, 200, 200, 403),
    "otro_socio": (0, 404, 404, 403),  # 404: para él ese préstamo no existe
    "bibliotecario": (1, 200, 200, 200),
}


@pytest.mark.parametrize("rol", ROLES)
def test_matriz_prestamos(rol):
    prestamo = PrestamoFactory()
    api = como(rol, prestamo.socio)
    lista = api.get("/api/v1/prestamos/")
    obtenidos = (
        len(lista.json()) if lista.status_code == 200 else lista.status_code,
        api.get(f"/api/v1/prestamos/{prestamo.pk}/").status_code,
        api.post(f"/api/v1/prestamos/{prestamo.pk}/devolver/").status_code,
        api.get("/api/v1/prestamos/vencidos/").status_code,
    )
    assert obtenidos == PRESTAMOS[rol]


def test_get_queryset_y_permiso_de_objeto_son_dos_capas(mocker):
    """Aunque un fallo en get_queryset dejara pasar un préstamo ajeno, el permiso de objeto lo para."""
    prestamo = PrestamoFactory()
    intruso = UsuarioFactory()
    mocker.patch(
        "prestamos.api.views.prestamos_visibles", side_effect=lambda u: type(prestamo).objects.all()
    )
    api = APIClient()
    api.force_authenticate(intruso)
    assert api.get(f"/api/v1/prestamos/{prestamo.pk}/").status_code == 200  # ver: lo dejamos
    assert api.post(f"/api/v1/prestamos/{prestamo.pk}/devolver/").status_code == 403  # tocar: no


# ── 3. Géneros con DjangoModelPermissions: se gestionan desde el admin ──
def test_generos_segun_los_permisos_del_grupo():
    usuario = UsuarioFactory()
    api = APIClient()
    api.force_authenticate(usuario)
    assert api.get("/api/v1/generos/").status_code == 200  # GET: cualquiera autenticado
    assert api.post("/api/v1/generos/", {"nombre": "Novela gráfica"}).status_code == 403

    grupo = Group.objects.create(name="catalogadores")  # lo que harías en /admin/auth/group/
    grupo.permissions.add(Permission.objects.get(codename="add_genero"))
    usuario.groups.add(grupo)
    usuario = type(usuario).objects.get(pk=usuario.pk)  # los permisos se cachean en el objeto
    api.force_authenticate(usuario)
    assert api.post("/api/v1/generos/", {"nombre": "Novela gráfica"}).status_code == 201
    genero = Genero.objects.get(nombre="Novela gráfica")
    assert api.delete(f"/api/v1/generos/{genero.pk}/").status_code == 403  # sin delete_genero


# ── 4. Throttling ──
def test_sexto_login_es_429():
    UsuarioFactory(email="ana@example.com")
    api = APIClient()
    for _ in range(5):
        r = api.post("/api/v1/auth/login/", {"email": "ana@example.com", "password": "mala"})
        assert r.status_code == 401
    r = api.post("/api/v1/auth/login/", {"email": "ana@example.com", "password": "mala"})
    assert r.status_code == 429 and int(r["Retry-After"]) > 0


def test_anonimos_por_ip():
    api = APIClient()
    respuestas = [api.get("/api/v1/estadisticas/").status_code for _ in range(31)]
    assert respuestas[:30] == [200] * 30 and respuestas[30] == 429  # anon: 30/min
    otra_ip = APIClient(REMOTE_ADDR="10.0.0.2")
    assert otra_ip.get("/api/v1/estadisticas/").status_code == 200
