"""Ejercicio del módulo 31: tests de servicios con factories, consultas, concurrencia y tiempo."""

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal

import pytest
import time_machine
from django.db import IntegrityError, connection
from django.utils import timezone

from catalogo.models import Ejemplar
from catalogo.tests.factories import EjemplarFactory
from prestamos.models import Multa, Prestamo
from prestamos.services import EjemplarNoDisponible, informe_socios, prestar
from prestamos.tasks import calcular_multas
from prestamos.tests.factories import PrestamoFactory
from usuarios.tests.factories import UsuarioFactory

pytestmark = pytest.mark.django_db


# ── 2. prestar() ──
def test_prestar_marca_ejemplar_como_prestado(socio):
    ejemplar = EjemplarFactory()

    prestamo = prestar(ejemplar.pk, socio)

    ejemplar.refresh_from_db()
    assert ejemplar.estado == Ejemplar.Estado.PRESTADO
    assert prestamo.socio == socio
    assert prestamo.fecha_limite > timezone.now() + Prestamo.DURACION - timedelta(minutes=1)


@pytest.mark.parametrize(
    "estado",
    [Ejemplar.Estado.PRESTADO, Ejemplar.Estado.REPARACION, Ejemplar.Estado.BAJA],
)
def test_solo_presta_disponibles(socio, estado):
    with pytest.raises(EjemplarNoDisponible):
        prestar(EjemplarFactory(estado=estado).pk, socio)
    assert not Prestamo.objects.exists()


def test_prestar_encola_confirmacion(socio, mocker, django_capture_on_commit_callbacks):
    # Las tareas de django.tasks son dataclasses congeladas: no se puede parchear .enqueue,
    # se sustituye la tarea entera en el módulo que la usa
    tarea = mocker.patch("prestamos.services.enviar_confirmacion_prestamo")
    with django_capture_on_commit_callbacks(execute=True):
        prestamo = prestar(EjemplarFactory().pk, socio)
    tarea.enqueue.assert_called_once_with(prestamo.pk)


def test_sin_commit_no_se_encola(socio, mocker, django_capture_on_commit_callbacks):
    tarea = mocker.patch("prestamos.services.enviar_confirmacion_prestamo")
    with django_capture_on_commit_callbacks(execute=False):
        prestar(EjemplarFactory().pk, socio)
    tarea.enqueue.assert_not_called()


# ── 2. informe_socios(): número de consultas fijo ──
@pytest.mark.parametrize("n_socios", [1, 20])
def test_informe_socios_sin_n_mas_1(n_socios, django_assert_num_queries):
    for socio in UsuarioFactory.create_batch(n_socios):
        PrestamoFactory.create_batch(2, socio=socio)
    with django_assert_num_queries(2):  # socios con su suma + préstamos activos (prefetch)
        informe = informe_socios()
    assert len(informe) == n_socios
    assert all(len(fila["activos"]) == 2 for fila in informe)


def test_informe_suma_solo_multas_pendientes(socio):
    pagada, pendiente = PrestamoFactory.create_batch(2, socio=socio, vencido=True)
    Multa.objects.create(prestamo=pagada, importe_base=Decimal("5"), pagada=True)
    Multa.objects.create(prestamo=pendiente, importe_base=Decimal("1.50"))
    (fila,) = informe_socios()
    assert fila["multas_pendientes"] == Decimal("1.50")


# ── 3. Concurrencia (PostgreSQL de verdad, cada hilo con su conexión) ──
@pytest.fixture
def ventana_de_carrera(mocker):
    """Hace lenta la creación del préstamo para que los dos hilos se solapen SIEMPRE."""
    crear = Prestamo.objects.create

    def lento(**kwargs):
        time.sleep(0.3)
        return crear(**kwargs)

    mocker.patch.object(Prestamo.objects, "create", side_effect=lento)


def dos_a_la_vez(ejemplar):
    socios = UsuarioFactory.create_batch(2)

    def intentar(socio):
        try:
            prestar(ejemplar.pk, socio)
            return "ok"
        except EjemplarNoDisponible:
            return "no"
        except IntegrityError:
            return "IntegrityError"
        finally:
            connection.close()  # cada hilo abrió su propia conexión

    with ThreadPoolExecutor(2) as pool:
        return sorted(pool.map(intentar, socios))


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_dos_prestamos_simultaneos_solo_uno_gana(ventana_de_carrera):
    assert dos_a_la_vez(EjemplarFactory()) == ["no", "ok"]
    assert Prestamo.objects.count() == 1


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_sin_select_for_update_solo_salva_la_restriccion(ventana_de_carrera, mocker):
    # Simula haber quitado select_for_update(): los dos hilos leen "disponible" a la vez
    mocker.patch.object(Ejemplar.objects, "select_for_update", return_value=Ejemplar.objects.all())
    resultados = dos_a_la_vez(EjemplarFactory())
    # El segundo choca con la UniqueConstraint del módulo 06: no hay dos préstamos (la BD lo
    # impide), pero el usuario recibe un 500 en vez de "no disponible"
    assert resultados == ["IntegrityError", "ok"]
    assert Prestamo.objects.count() == 1


# ── 4. Multas en el borde del plazo ──
def test_multa_en_el_borde_del_plazo():
    limite = timezone.make_aware(timezone.datetime(2026, 11, 15, 9, 0))
    prestamo = PrestamoFactory(fecha_limite=limite)

    with time_machine.travel(limite - timedelta(seconds=1), tick=False):
        assert calcular_multas() == 0  # el último segundo del plazo: sin multa
    with time_machine.travel(limite + timedelta(seconds=1), tick=False):
        assert calcular_multas() == 1  # un segundo tarde: ya hay multa (mínimo, un día)
    assert Multa.objects.get(prestamo=prestamo).importe_base == Decimal("0.50")
    with time_machine.travel(limite + timedelta(days=4), tick=False):
        calcular_multas()
    assert Multa.objects.get(prestamo=prestamo).importe_base == Decimal("2.00")  # 0,50 €/día
