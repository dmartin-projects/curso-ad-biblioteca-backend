"""Ejercicio del módulo 09."""

import time
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import FieldFetchBlocked
from django.db import connection, models
from django.db.models import Prefetch
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from catalogo.models import Ejemplar, Libro
from prestamos.models import Multa, Prestamo
from prestamos.services import EjemplarNoDisponible, informe_socios, prestar
from usuarios.models import Usuario

pytestmark = pytest.mark.django_db


def crear_socios(n):
    libro = Libro.objects.create(titulo=f"Libro {n}", isbn=f"97884{n:08d}")
    for i in range(n):
        socio = Usuario.objects.create_user(f"socio{n}-{i}", email=f"s{n}-{i}@example.com")
        for j in range(2):
            e = Ejemplar.objects.create(libro=libro, codigo=f"{n}-{i}-{j}")
            p = Prestamo.objects.create(
                ejemplar=e, socio=socio, fecha_limite=timezone.now() + timedelta(days=5)
            )
        Multa.objects.create(prestamo=p, importe_base=Decimal("1.50"), recargo=Decimal("0.50"))


def test_informe_con_consultas_constantes():
    crear_socios(3)
    with CaptureQueriesContext(connection) as pocos:
        informe = informe_socios()
    assert len(informe) == 3 and informe[0]["multas_pendientes"] == Decimal("2.00")
    assert len(informe[0]["activos"]) == 2
    crear_socios(30)
    with CaptureQueriesContext(connection) as muchos:
        assert len(informe_socios()) == 33
    assert len(pocos) == len(muchos) == 2


def test_la_version_ingenua_hace_n_mas_1():
    crear_socios(10)
    with CaptureQueriesContext(connection) as consultas:
        for s in Usuario.objects.all():
            for p in s.prestamos.filter(estado="activo"):
                p.ejemplar.libro.titulo  # noqa: B018
    assert len(consultas) == 1 + 10  # el manager de Prestamo ya trae ejemplar y libro: "solo" 1 + N


def test_fetch_raise_no_encuentra_cargas_perezosas():
    crear_socios(3)
    raise_ = models.FETCH_RAISE
    # el modo NO se hereda en los prefetch: hay que ponerlo también en la consulta interna
    socios = Usuario.objects.fetch_mode(raise_).prefetch_related(
        Prefetch(
            "prestamos",
            queryset=Prestamo.objects.filter(estado="activo")
            .select_related("ejemplar__libro")
            .fetch_mode(raise_),
            to_attr="activos",
        )
    )
    for s in socios:
        for p in s.activos:
            assert p.ejemplar.libro.titulo

    # sin el select_related, salta en el primer acceso perezoso
    sin = Usuario.objects.fetch_mode(raise_).prefetch_related(
        Prefetch(
            "prestamos",
            queryset=Prestamo.objects.select_related(None).fetch_mode(raise_),
            to_attr="activos",
        )
    )
    with pytest.raises(FieldFetchBlocked, match="Fetching of Prestamo.ejemplar blocked"):
        for s in sin:
            for p in s.activos:
                p.ejemplar  # noqa: B018


def test_prestar(django_capture_on_commit_callbacks, capsys):
    libro = Libro.objects.create(titulo="Dune", isbn="9788497593793")
    ejemplar = Ejemplar.objects.create(libro=libro, codigo="D1")
    socio = Usuario.objects.create_user("ana")
    with django_capture_on_commit_callbacks(execute=True):
        prestamo = prestar(ejemplar.pk, socio)
    assert f"Préstamo {prestamo.pk} confirmado" in capsys.readouterr().out
    ejemplar.refresh_from_db()
    assert ejemplar.estado == Ejemplar.Estado.PRESTADO
    with pytest.raises(EjemplarNoDisponible):
        prestar(ejemplar.pk, socio)


def test_bulk_create_frente_a_create():
    """No es un test de rendimiento fiable (depende de la máquina): imprime los tiempos para compararlos."""
    libro = Libro.objects.create(titulo="Dune", isbn="9788497593793")
    inicio = time.perf_counter()
    for i in range(10_000):
        Ejemplar.objects.create(libro=libro, codigo=f"C-{i}")
    uno_a_uno = time.perf_counter() - inicio
    inicio = time.perf_counter()
    Ejemplar.objects.bulk_create(
        [Ejemplar(libro=libro, codigo=f"B-{i}") for i in range(10_000)], batch_size=2000
    )
    en_lote = time.perf_counter() - inicio
    print(f"\n10.000 create(): {uno_a_uno:.2f} s · 10.000 en bulk_create: {en_lote:.2f} s")
    assert Ejemplar.objects.count() == 20_000
