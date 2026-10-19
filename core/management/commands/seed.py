# core/management/commands/seed.py
import random
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from faker import Faker

from catalogo.busqueda import actualizar_busqueda
from catalogo.models import Autor, Ejemplar, Genero, Libro
from prestamos.models import Prestamo
from usuarios.models import Usuario


class Command(BaseCommand):
    help = "Rellena la base de datos con datos de prueba"

    def add_arguments(self, parser):
        parser.add_argument("--libros", type=int, default=200)
        parser.add_argument("--socios", type=int, default=50)
        parser.add_argument("--prestamos", type=int, default=300)
        parser.add_argument("--borrar", action="store_true")

    @transaction.atomic
    def handle(self, *args, libros, socios, prestamos, borrar, **options):
        if not settings.DEBUG:
            raise CommandError("seed solo se ejecuta en desarrollo")

        fake = Faker("es_ES")
        Faker.seed(42)  # datos reproducibles
        random.seed(42)

        if borrar:
            Prestamo.objects.all().delete()
            Ejemplar.objects.all().delete()
            Libro.objects.all().delete()
            Autor.objects.filter(slug__startswith="autor-").delete()
            Usuario.objects.filter(email__startswith="socio", is_staff=False).delete()

        generos = list(Genero.objects.all())
        autores = Autor.objects.bulk_create(
            Autor(nombre=fake.name(), slug=f"autor-{i}") for i in range(max(libros // 3, 1))
        )
        nuevos = Libro.objects.bulk_create(
            Libro(
                titulo=fake.sentence(nb_words=4).rstrip("."),
                isbn=fake.unique.isbn13(separator=""),
                publicado=fake.date_between("-60y", "today"),
                sinopsis=fake.paragraph(nb_sentences=3),
            )
            for _ in range(libros)
        )
        Libro.autores.through.objects.bulk_create(
            Libro.autores.through(libro=libro, autor=random.choice(autores)) for libro in nuevos
        )
        Libro.generos.through.objects.bulk_create(
            Libro.generos.through(libro=libro, genero=random.choice(generos))
            for libro in nuevos
            if generos
        )
        ejemplares = Ejemplar.objects.bulk_create(
            Ejemplar(libro=libro, codigo=f"E-{libro.pk}-{n}")
            for libro in nuevos
            for n in range(random.randint(1, 3))
        )
        # create_user (no bulk): calcula el hash y la signal crea el PerfilSocio (módulo 15)
        lectores = [
            Usuario.objects.create_user(
                email=f"socio{i}@example.com", password="demo1234", nombre=fake.first_name()
            )
            for i in range(socios)
        ]

        # Préstamos: un ejemplar distinto para cada uno; uno de cada tres, ya devuelto
        ahora = timezone.now()
        nuevos_prestamos = []
        for ejemplar in random.sample(ejemplares, min(prestamos, len(ejemplares))):
            inicio = ahora - timedelta(days=random.randint(0, 60))
            devuelto = random.random() < 0.33
            nuevos_prestamos.append(
                Prestamo(
                    ejemplar=ejemplar,
                    socio=random.choice(lectores),
                    fecha_inicio=inicio,
                    fecha_limite=inicio + Prestamo.DURACION,
                    estado=Prestamo.Estado.DEVUELTO if devuelto else Prestamo.Estado.ACTIVO,
                    fecha_devolucion=inicio + timedelta(days=random.randint(1, 30))
                    if devuelto
                    else None,
                )
            )
            if not devuelto:
                ejemplar.estado = Ejemplar.Estado.PRESTADO
        Prestamo.objects.bulk_create(nuevos_prestamos)
        Ejemplar.objects.bulk_update(ejemplares, ["estado"], batch_size=1000)

        # bulk_create no emite post_save: el vector de búsqueda (módulo 15) hay que calcularlo aquí
        for libro in nuevos:
            actualizar_busqueda(libro.pk)

        self.stdout.write(
            self.style.SUCCESS(
                f"{libros} libros, {len(ejemplares)} ejemplares, {socios} socios "
                f"y {len(nuevos_prestamos)} préstamos creados"
            )
        )
