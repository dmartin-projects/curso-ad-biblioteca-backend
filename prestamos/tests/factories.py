# prestamos/tests/factories.py
from datetime import timedelta

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from catalogo.models import Ejemplar
from catalogo.tests.factories import EjemplarFactory
from prestamos.models import Prestamo
from usuarios.tests.factories import UsuarioFactory


class PrestamoFactory(DjangoModelFactory):
    class Meta:
        model = Prestamo

    ejemplar = factory.SubFactory(EjemplarFactory, estado=Ejemplar.Estado.PRESTADO)
    socio = factory.SubFactory(UsuarioFactory)
    fecha_limite = factory.LazyFunction(lambda: timezone.now() + timedelta(days=14))

    class Params:
        vencido = factory.Trait(
            fecha_limite=factory.LazyFunction(lambda: timezone.now() - timedelta(days=3))
        )
