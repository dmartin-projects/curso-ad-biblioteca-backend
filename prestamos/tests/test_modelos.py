from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.forms import modelform_factory
from django.utils import timezone

from catalogo.models import Ejemplar, Libro
from prestamos.models import Prestamo, PrestamoActivo
from usuarios.models import Usuario

pytestmark = pytest.mark.django_db


@pytest.fixture
def ejemplar():
    libro = Libro.objects.create(titulo="Dune", isbn="9788497593793")
    return Ejemplar.objects.create(libro=libro, codigo="E-1")


@pytest.fixture
def socio():
    return Usuario.objects.create_user("ana", password="x")


def test_un_solo_prestamo_activo_por_ejemplar(ejemplar, socio):
    limite = timezone.now() + Prestamo.DURACION
    Prestamo.objects.create(ejemplar=ejemplar, socio=socio, fecha_limite=limite)

    # 1) Como el admin: un ModelForm valida las constraints y muestra el mensaje
    Form = modelform_factory(Prestamo, fields=["ejemplar", "socio", "fecha_limite", "estado"])
    form = Form(
        data={
            "ejemplar": ejemplar.pk,
            "socio": socio.pk,
            "fecha_limite": limite,
            "estado": "activo",
        }
    )
    assert not form.is_valid()
    assert form.errors["__all__"] == ["Este ejemplar ya está prestado."]

    # 2) Como el shell: sin validación en Python, PostgreSQL rechaza el INSERT
    with (
        pytest.raises(IntegrityError, match="un_prestamo_activo_por_ejemplar"),
        transaction.atomic(),
    ):
        Prestamo.objects.create(ejemplar=ejemplar, socio=socio, fecha_limite=limite)

    # devuelto el primero, se puede volver a prestar
    Prestamo.objects.update(estado=Prestamo.Estado.DEVUELTO, fecha_devolucion=timezone.now())
    Prestamo.objects.create(ejemplar=ejemplar, socio=socio, fecha_limite=limite)


def test_proxy_solo_activos(ejemplar, socio):
    limite = timezone.now() + timedelta(days=21)
    Prestamo.objects.create(ejemplar=ejemplar, socio=socio, fecha_limite=limite, estado="devuelto")
    activo = Prestamo.objects.create(ejemplar=ejemplar, socio=socio, fecha_limite=limite)
    assert list(PrestamoActivo.objects.values_list("pk", flat=True)) == [activo.pk]
    assert Prestamo.objects.count() == 2  # misma tabla


def test_titulo_busqueda_lo_calcula_la_bd():
    libro = Libro.objects.create(titulo="El Señor de los Anillos", isbn="9788445073728")
    assert libro.titulo_busqueda == "el señor de los anillos"  # save() lo trae con RETURNING
    assert Libro.objects.filter(titulo_busqueda__startswith="el señor").count() == 1
    libro.titulo = "Dune"
    libro.save()
    assert libro.titulo_busqueda == "dune"  # también al actualizar, sin refresh_from_db()
