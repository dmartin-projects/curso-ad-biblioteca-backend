# catalogo/tests/factories.py
import factory
from factory.django import DjangoModelFactory

from catalogo.models import Autor, Ejemplar, Libro


def isbn13_valido(n: int) -> str:
    base = f"978{n:09d}"
    control = (10 - sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(base)) % 10) % 10
    return base + str(control)


class AutorFactory(DjangoModelFactory):
    class Meta:
        model = Autor
        django_get_or_create = ("slug",)

    nombre = factory.Faker("name", locale="es_ES")
    slug = factory.Sequence(lambda n: f"autor-{n}")


class LibroFactory(DjangoModelFactory):
    class Meta:
        model = Libro
        skip_postgeneration_save = True

    titulo = factory.Faker("sentence", nb_words=3, locale="es_ES")
    isbn = factory.Sequence(isbn13_valido)
    paginas = factory.Faker("pyint", min_value=80, max_value=900)

    @factory.post_generation
    def autores(self, create, extracted, **kwargs):
        if not create:
            return
        for autor in extracted or [AutorFactory()]:
            self.autores.add(autor)


class EjemplarFactory(DjangoModelFactory):
    class Meta:
        model = Ejemplar

    libro = factory.SubFactory(LibroFactory)
    codigo = factory.Sequence(lambda n: f"EJ-{n:05d}")
