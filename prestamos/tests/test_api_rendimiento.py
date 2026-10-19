"""Ejercicio del módulo 39: consultas constantes, caché, ETag y matriz completa de préstamos."""

import pytest
from django.contrib.auth.models import Group
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from catalogo.tests.factories import AutorFactory, EjemplarFactory, LibroFactory
from prestamos.models import Prestamo
from prestamos.services import devolver
from prestamos.tests.factories import PrestamoFactory
from usuarios.tests.factories import UsuarioFactory

pytestmark = pytest.mark.django_db


def cliente(usuario=None):
    api = APIClient()
    if usuario:
        api.force_authenticate(usuario)
    return api


def consultas(api, url) -> int:
    with CaptureQueriesContext(connection) as capturadas:
        r = api.get(url)
    assert r.status_code == 200, r.content
    return len(capturadas)


# ── 5. Consultas constantes en TODOS los listados (3 filas frente a 30) ──
def crear_libros(n):
    for _ in range(n):
        EjemplarFactory(libro=LibroFactory(autores=[AutorFactory()]))


def crear_prestamos(n, socio):
    PrestamoFactory.create_batch(n, socio=socio, vencido=True)


@pytest.mark.parametrize(
    ("url", "crear"),
    [
        ("/api/v1/libros/", lambda n, socio: crear_libros(n)),
        ("/api/v1/autores/", lambda n, socio: AutorFactory.create_batch(n)),
        ("/api/v1/prestamos/", crear_prestamos),
        ("/api/v1/prestamos/vencidos/", crear_prestamos),
    ],
)
def test_listados_con_consultas_constantes(url, crear, bibliotecario):
    api = cliente(bibliotecario)
    crear(3, bibliotecario)
    pocas = consultas(api, url)
    crear(27, bibliotecario)
    assert consultas(api, url) == pocas  # 🔑 no crece con las filas


def test_only_no_provoca_cargas_perezosas(bibliotecario, django_assert_num_queries):
    """Con only() en el listado, acceder a un campo diferido sería una consulta por fila."""
    crear_prestamos(10, bibliotecario)
    with django_assert_num_queries(1):  # is_staff: ni siquiera consulta grupos. Solo la página
        cliente(bibliotecario).get("/api/v1/prestamos/")


# ── 3. Caché ──
def test_generos_cacheados_por_idioma(socio):
    api = cliente(socio)
    assert consultas(api, "/api/v1/generos/") == 1
    assert consultas(api, "/api/v1/generos/") == 0  # de la caché: ni la consulta
    r = api.get("/api/v1/generos/", headers={"accept-language": "en"})
    assert "Accept-Language" in r["Vary"]  # cada idioma, su copia


def test_estadisticas_cacheadas_e_invalidadas(django_capture_on_commit_callbacks):
    api = cliente()
    with django_capture_on_commit_callbacks(execute=True):
        prestamo = PrestamoFactory()  # su ejemplar, prestado
        EjemplarFactory()  # otro libro, disponible
    assert api.get("/api/v1/estadisticas/").json() == {"libros": 2, "con_ejemplares_disponibles": 1}
    assert (
        consultas(api, "/api/v1/estadisticas/") <= 1
    )  # versión del catálogo; el cálculo, cacheado

    with django_capture_on_commit_callbacks(execute=True):
        devolver(prestamo)  # el ejemplar vuelve a estar disponible → post_save → nueva versión
    assert api.get("/api/v1/estadisticas/").json()["con_ejemplares_disponibles"] == 2


# ── 4. ETag ──
def test_etag_304(socio, django_capture_on_commit_callbacks):
    libro = LibroFactory()
    api = cliente(socio)
    r = api.get(f"/api/v1/libros/{libro.pk}/")
    etag = r["ETag"]
    r = api.get(f"/api/v1/libros/{libro.pk}/", headers={"if-none-match": etag})
    assert r.status_code == 304 and not r.content

    for cabecera in (f'"otro", {etag}', f"W/{etag}", "*"):  # lista, ETag débil y comodín
        r = api.get(f"/api/v1/libros/{libro.pk}/", headers={"if-none-match": cabecera})
        assert r.status_code == 304, cabecera

    with django_capture_on_commit_callbacks(execute=True):
        libro.autores.add(AutorFactory())  # no cambia 'actualizado', pero sí la versión
    r = api.get(f"/api/v1/libros/{libro.pk}/", headers={"if-none-match": etag})
    assert r.status_code == 200 and r["ETag"] != etag
    assert api.get("/api/v1/libros/999999/").status_code == 404  # sin ETag, el 404 de siempre


# ── 5. Matriz completa de préstamos ──
ROLES = ["anonimo", "socio", "otro_socio", "bibliotecario"]
#           ver  listar devolver renovar exportar vencidos  crear  put  delete
MATRIZ = {
    "anonimo": (401, 401, 401, 401, 401, 401, 401, 401, 401),
    "socio": (200, 200, 200, 200, 200, 403, 201, 405, 405),
    "otro_socio": (404, 200, 404, 404, 200, 403, 201, 405, 405),
    "bibliotecario": (200, 200, 200, 200, 200, 200, 201, 405, 405),
}


@pytest.mark.parametrize("rol", ROLES)
@pytest.mark.parametrize("accion", ["devolver", "renovar"])
def test_matriz_prestamos(rol, accion):
    prestamo = PrestamoFactory()
    usuario = {"socio": prestamo.socio, "anonimo": None}.get(rol, UsuarioFactory())
    if rol == "bibliotecario":
        usuario.groups.add(Group.objects.get(name="bibliotecarios"))
    api = cliente(usuario)
    base = f"/api/v1/prestamos/{prestamo.pk}/"
    obtenidos = (
        api.get(base).status_code,
        api.get("/api/v1/prestamos/").status_code,
        api.post(base + f"{accion}/").status_code if accion == "devolver" else None,
        api.post(base + f"{accion}/").status_code if accion == "renovar" else None,
        api.get("/api/v1/prestamos/exportar/").status_code,
        api.get("/api/v1/prestamos/vencidos/").status_code,
        api.post("/api/v1/prestamos/", {"ejemplar_id": EjemplarFactory().pk}).status_code,
        api.put(base, {}).status_code,
        api.delete(base).status_code,
    )
    esperado = list(MATRIZ[rol])
    esperado[2 if accion == "renovar" else 3] = None  # cada caso prueba una de las dos acciones
    assert obtenidos == tuple(esperado)
    if rol in ("socio", "bibliotecario"):
        prestamo.refresh_from_db()
        assert prestamo.estado == ("devuelto" if accion == "devolver" else "activo")
    else:
        assert Prestamo.objects.get(pk=prestamo.pk).estado == "activo"  # nadie más lo toca
