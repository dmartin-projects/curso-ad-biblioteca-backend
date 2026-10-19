"""Ejercicio del módulo 18."""

from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from catalogo.models import Autor, Ejemplar, Libro
from prestamos.models import Prestamo
from usuarios.models import Usuario

pytestmark = pytest.mark.django_db


def crear_libros(n, desde=0):
    herbert, _ = Autor.objects.get_or_create(nombre="Frank Herbert", slug="herbert")
    for i in range(desde, desde + n):
        libro = Libro.objects.create(titulo=f"Libro {i:03d}", isbn=f"97884{i:08d}")
        libro.autores.add(herbert)
        Ejemplar.objects.create(libro=libro, codigo=f"E{i}")


@pytest.fixture
def admin_client(client):
    client.force_login(Usuario.objects.create_superuser("admin@example.com", "x"))
    return client


def test_listado_de_libros_con_consultas_constantes(admin_client):
    crear_libros(3)
    with CaptureQueriesContext(connection) as pocos:
        assert admin_client.get("/admin/catalogo/libro/").status_code == 200
    crear_libros(30, desde=3)
    with CaptureQueriesContext(connection) as muchos:
        r = admin_client.get("/admin/catalogo/libro/")
    assert b"Frank Herbert" in r.content
    assert len(pocos) == len(muchos)  # no crece con el número de libros


def test_paginas_del_admin(admin_client):
    crear_libros(1)
    libro = Libro.objects.get()
    for url in [
        "/admin/catalogo/libro/add/",
        f"/admin/catalogo/libro/{libro.pk}/change/",
        "/admin/catalogo/autor/",
        "/admin/catalogo/ejemplar/",
        "/admin/prestamos/prestamo/",
        "/admin/prestamos/prestamo/?situacion=vencido",
        "/admin/prestamos/prestamo/estadisticas/",
    ]:
        assert admin_client.get(url).status_code == 200, url


@pytest.fixture
def prestamos():
    crear_libros(2)
    socio = Usuario.objects.create_user("ana@example.com")
    ahora = timezone.now()
    e1, e2 = Ejemplar.objects.order_by("codigo")
    vencido = Prestamo.objects.create(
        ejemplar=e1,
        socio=socio,
        fecha_inicio=ahora - timedelta(days=60),
        fecha_limite=ahora - timedelta(days=39),
    )
    en_plazo = Prestamo.objects.create(
        ejemplar=e2, socio=socio, fecha_limite=ahora + timedelta(days=10)
    )
    return vencido, en_plazo


def accion(client, nombre, prestamos):
    return client.post(
        "/admin/prestamos/prestamo/",
        {"action": nombre, "_selected_action": [p.pk for p in prestamos]},
    )


def test_filtro_de_retraso(admin_client, prestamos):
    vencido, en_plazo = prestamos
    r = admin_client.get("/admin/prestamos/prestamo/?situacion=muy_vencido")
    assert list(r.context["cl"].result_list) == [vencido]
    r = admin_client.get("/admin/prestamos/prestamo/?situacion=en_plazo")
    assert list(r.context["cl"].result_list) == [en_plazo]


def test_acciones(admin_client, prestamos):
    vencido, en_plazo = prestamos
    limite, limite_vencido = en_plazo.fecha_limite, vencido.fecha_limite
    r = accion(admin_client, "renovar", [en_plazo, vencido])
    en_plazo.refresh_from_db()
    vencido.refresh_from_db()
    assert en_plazo.fecha_limite == limite + Prestamo.DURACION
    assert vencido.fecha_limite == limite_vencido  # la regla del service: vencido no se renueva
    avisos = [str(m) for m in r.wsgi_request._messages]
    assert "1 préstamos renovados." in avisos
    assert any("vencido no se renueva" in aviso for aviso in avisos)

    r = accion(admin_client, "exportar_csv", [vencido, en_plazo])
    filas = r.content.decode().splitlines()
    assert filas[0] == "Libro,Ejemplar,Socio,Inicio,Límite,Estado" and len(filas) == 3

    accion(admin_client, "marcar_devueltos", [vencido])
    vencido.refresh_from_db()
    assert vencido.estado == "devuelto" and vencido.ejemplar.estado == "disponible"


def test_renovar_solo_con_permiso(client, prestamos):
    staff = Usuario.objects.create_user("staff@example.com", is_staff=True)
    staff.groups.add(Group.objects.get(name="socios"))  # sin renovar_prestamo ni view_prestamo
    client.force_login(staff)
    assert client.get("/admin/prestamos/prestamo/").status_code == 403  # ni siquiera ve la lista
    staff.groups.add(Group.objects.get(name="bibliotecarios"))
    r = client.get("/admin/prestamos/prestamo/")
    acciones = [valor for valor, _ in r.context["action_form"].fields["action"].choices]
    assert "renovar" in acciones
    assert "delete_selected" not in acciones  # has_delete_permission = False
