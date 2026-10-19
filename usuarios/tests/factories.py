# usuarios/tests/factories.py
import factory
from factory.django import DjangoModelFactory

from usuarios.models import Usuario


class UsuarioFactory(DjangoModelFactory):
    class Meta:
        model = Usuario
        django_get_or_create = ("email",)

    email = factory.Sequence(
        lambda n: f"socio{n}@example.com"
    )  # el Usuario del módulo 12 entra por email
    nombre = factory.Faker("first_name", locale="es_ES")
    apellidos = factory.Faker("last_name", locale="es_ES")
    password = factory.django.Password("clave-segura-123")  # guarda el hash, como set_password

    class Params:
        bibliotecario = factory.Trait(is_staff=True)  # UsuarioFactory(bibliotecario=True)
