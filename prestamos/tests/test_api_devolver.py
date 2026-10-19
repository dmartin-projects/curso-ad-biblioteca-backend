"""Ejercicio del módulo 32: primeros endpoints de DRF y el servicio devolver()."""

from datetime import timedelta
from decimal import Decimal

import pytest
import time_machine
from django.contrib.auth.models import Group
from django.utils import timezone
from rest_framework.test import APIClient

from catalogo.models import Ejemplar
from catalogo.tests.factories import EjemplarFactory, LibroFactory
from prestamos.models import Multa, Prestamo
from prestamos.services import PrestamoYaDevuelto, devolver
from prestamos.tasks import calcular_multas
from prestamos.tests.factories import PrestamoFactory
from usuarios.tests.factories import UsuarioFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def api():
    return APIClient()


# ── 2. Estadísticas públicas ──
@pytest.mark.parametrize("url", ["/api/v1/estadisticas/", "/api/v1/estadisticas-cbv/"])
def test_estadisticas_publicas(api, url):
    libro = LibroFactory()
    EjemplarFactory(libro=libro)
    EjemplarFactory(libro=libro)  # dos disponibles del mismo libro cuentan una vez
    EjemplarFactory(estado=Ejemplar.Estado.PRESTADO)
    r = api.get(url)
    assert r.status_code == 200
    assert r.json() == {"libros": 2, "con_ejemplares_disponibles": 1}


def test_version_desconocida_da_404(api):
    assert api.get("/api/v9/estadisticas/").status_code == 404
    assert api.post("/api/v1/estadisticas/").status_code == 405  # @api_view(["GET"])


# ── 3. Devolver ──
def test_devolver_en_plazo(api):
    prestamo = PrestamoFactory()
    api.force_authenticate(prestamo.socio)
    r = api.post(f"/api/v1/prestamos/{prestamo.pk}/devolver/")
    assert r.status_code == 200
    datos = r.json()  # desde el módulo 34, el préstamo completo (PrestamoSerializer)
    assert (datos["id"], datos["estado"], datos["multa"]) == (prestamo.pk, "devuelto", None)
    prestamo.ejemplar.refresh_from_db()
    assert prestamo.ejemplar.estado == Ejemplar.Estado.DISPONIBLE

    r = api.post(f"/api/v1/prestamos/{prestamo.pk}/devolver/")
    assert r.status_code == 409 and r.json() == {"detail": "El préstamo ya estaba devuelto."}


def test_devolver_tarde_genera_multa_como_cadena(api):
    prestamo = PrestamoFactory(fecha_limite=timezone.now() - timedelta(days=3, hours=2))
    api.force_authenticate(prestamo.socio)
    r = api.post(f"/api/v1/prestamos/{prestamo.pk}/devolver/")
    assert r.json()["multa"] == "1.50"  # 3 días × 0,50 €, como cadena


def test_misma_multa_que_la_tarea_nocturna():
    limite = timezone.now() - timedelta(days=2, hours=5)
    prestamo = PrestamoFactory(fecha_limite=limite)
    calcular_multas()  # la tarea de la noche ya creó la multa…
    with time_machine.travel(timezone.now() + timedelta(days=1), tick=False):
        devolver(prestamo)  # …y al devolver un día después se actualiza, no se duplica
    assert Multa.objects.get(prestamo=prestamo).importe_base == Decimal("1.50")


def test_ajeno_da_404_y_bibliotecario_puede(api):
    prestamo = PrestamoFactory()
    api.force_authenticate(UsuarioFactory())
    assert api.post(f"/api/v1/prestamos/{prestamo.pk}/devolver/").status_code == 404

    bibliotecaria = UsuarioFactory()
    bibliotecaria.groups.add(Group.objects.get(name="bibliotecarios"))
    api.force_authenticate(bibliotecaria)
    assert api.post(f"/api/v1/prestamos/{prestamo.pk}/devolver/").status_code == 200


def test_anonimo_recibe_401(api):
    prestamo = PrestamoFactory()
    r = api.post(f"/api/v1/prestamos/{prestamo.pk}/devolver/")
    # Con solo SessionAuthentication era 403; desde el módulo 35 JWT va primero → 401
    assert r.status_code == 401 and r["WWW-Authenticate"].startswith("Bearer")
    assert Prestamo.objects.get().estado == Prestamo.Estado.ACTIVO


def test_servicio_rechaza_doble_devolucion():
    prestamo = devolver(PrestamoFactory())
    with pytest.raises(PrestamoYaDevuelto):
        devolver(prestamo)
