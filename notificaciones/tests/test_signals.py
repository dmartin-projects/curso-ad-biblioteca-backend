"""Ejercicio del módulo 15."""

import logging
from datetime import timedelta

import pytest
from django.contrib.postgres.search import SearchQuery
from django.utils import timezone

from catalogo.models import Autor, Ejemplar, Libro
from prestamos.models import Prestamo
from prestamos.services import LimitePrestamosAlcanzado, avisar_vencidos, devolver, prestar
from prestamos.signals import prestamo_devuelto
from usuarios.models import PerfilSocio, Usuario

pytestmark = pytest.mark.django_db


def test_perfil_de_socio_automatico():
    ana = Usuario.objects.create_user("ana@example.com")
    luis = Usuario.objects.create_user("luis@example.com")
    assert ana.socio.numero == f"S-{ana.pk:06d}"
    assert luis.socio.numero == f"S-{luis.pk:06d}"
    ana.nombre = "Ana"
    ana.save()  # una edición no crea otro perfil
    assert PerfilSocio.objects.count() == 2


def test_prestar_respeta_el_maximo_del_perfil():
    ana = Usuario.objects.create_user("ana@example.com")  # el signal le crea el perfil
    ana.socio.max_prestamos = 1
    ana.socio.save(update_fields=["max_prestamos"])
    libro = Libro.objects.create(titulo="Dune", isbn="9788497593793")
    primero, segundo = (Ejemplar.objects.create(libro=libro, codigo=c) for c in ("D1", "D2"))
    prestar(primero.pk, ana)
    with pytest.raises(LimitePrestamosAlcanzado):
        prestar(segundo.pk, ana)
    segundo.refresh_from_db()
    assert segundo.estado == Ejemplar.Estado.DISPONIBLE  # no se ha tocado nada


def encontrado(texto):
    return list(
        Libro.objects.filter(busqueda=SearchQuery(texto, config="spanish")).values_list(
            "titulo", flat=True
        )
    )


def test_busqueda_se_actualiza_con_el_libro_y_sus_autores():
    libro = Libro.objects.create(titulo="Dune", isbn="9788497593793", sinopsis="Arena y especia.")
    assert encontrado("especia") == ["Dune"]
    herbert = Autor.objects.create(nombre="Frank Herbert", slug="herbert")
    libro.autores.add(herbert)  # m2m_changed (post_add)
    assert encontrado("herbert") == ["Dune"]
    herbert.libros.remove(libro)  # m2m_changed desde el otro lado (reverse=True)
    assert encontrado("herbert") == []
    herbert.libros.add(libro)
    herbert.nombre = "Franklin Herbert"
    herbert.save()  # renombrar al autor también recalcula sus libros
    assert encontrado("franklin") == ["Dune"]


@pytest.fixture
def prestamo():
    libro = Libro.objects.create(titulo="Dune", isbn="9788497593793")
    ejemplar = Ejemplar.objects.create(libro=libro, codigo="D1", estado="prestado")
    socio = Usuario.objects.create_user("ana@example.com")
    ahora = timezone.now()
    return Prestamo.objects.create(
        ejemplar=ejemplar,
        socio=socio,
        fecha_inicio=ahora - timedelta(days=25),
        fecha_limite=ahora - timedelta(days=4),
    )


def test_devolver_emite_la_signal_y_la_app_notificaciones_reacciona(prestamo, caplog):
    recibidos = []
    prestamo_devuelto.connect(
        lambda sender, prestamo, **kw: recibidos.append(prestamo.pk), weak=False, dispatch_uid="t"
    )
    try:
        with caplog.at_level(logging.INFO, logger="notificaciones"):
            devolver(prestamo)
    finally:
        prestamo_devuelto.disconnect(dispatch_uid="t")
    assert recibidos == [prestamo.pk]
    assert f"Préstamo {prestamo.pk} devuelto: Dune" in caplog.text
    prestamo.ejemplar.refresh_from_db()
    assert prestamo.ejemplar.estado == Ejemplar.Estado.DISPONIBLE


def test_avisar_vencidos(prestamo, caplog):
    with caplog.at_level(logging.INFO, logger="notificaciones"):
        assert avisar_vencidos() == 1
    assert f"Préstamo {prestamo.pk} vencido hace 4 días (socio ana@example.com)" in caplog.text
