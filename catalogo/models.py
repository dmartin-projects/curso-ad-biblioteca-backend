# catalogo/models.py
import uuid
from pathlib import Path

from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex, OpClass
from django.contrib.postgres.search import SearchVectorField
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models import Count, Exists, OuterRef, Q
from django.db.models.functions import Lower
from django.urls import reverse

from core.models import ModeloConFechas
from core.validators import TamanoMaximoValidator, validar_pdf_real

from .fields import ISBNField


def ruta_portada(instance, filename: str) -> str:
    # Nunca uses el nombre original: puede colisionar o contener caracteres peligrosos
    extension = Path(filename).suffix.lower()
    return f"portadas/{instance.isbn}/{uuid.uuid4().hex}{extension}"


class Autor(ModeloConFechas):
    nombre = models.CharField(max_length=200)
    apellidos = models.CharField(max_length=200, blank=True)
    slug = models.SlugField(unique=True)
    biografia = models.TextField(blank=True)
    nacimiento = models.DateField(null=True, blank=True)
    notas = GenericRelation("core.Nota", related_query_name="autor")

    class Meta:
        ordering = ["nombre"]
        verbose_name_plural = "autores"
        indexes = [GinIndex(OpClass("nombre", name="gin_trgm_ops"), name="autor_nombre_trgm")]

    def __str__(self):
        return self.nombre


class GeneroManager(models.Manager):
    def get_by_natural_key(self, nombre):
        return self.get(nombre=nombre)


class Genero(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    padre = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="subgeneros"
    )

    objects = GeneroManager()

    def __str__(self):
        return self.nombre

    def natural_key(self):
        return (self.nombre,)


class LibroQuerySet(models.QuerySet):
    def disponibles(self):
        hay_disponible = Ejemplar.objects.filter(
            libro=OuterRef("pk"), estado=Ejemplar.Estado.DISPONIBLE
        )
        return self.filter(Exists(hay_disponible))

    def de_autor(self, slug: str):
        return self.filter(autores__slug=slug).distinct()

    def buscar(self, texto: str):
        return self.filter(
            Q(titulo__icontains=texto) | Q(autores__nombre__icontains=texto)
        ).distinct()

    def con_estadisticas(self):
        return self.annotate(
            n_ejemplares=Count("ejemplares", distinct=True),
            n_prestamos=Count("ejemplares__prestamos", distinct=True),
        )

    def con_disponibles(self):
        """ejemplares_disponibles en la misma consulta (para LibroListaSerializer, módulo 33)."""
        return self.annotate(
            ejemplares_disponibles=Count(
                "ejemplares", filter=Q(ejemplares__estado="disponible"), distinct=True
            )
        )

    def para_listado(self):
        """Todo lo que necesita la vista de listado, optimizado."""
        return self.prefetch_related("autores", "generos").con_estadisticas()


class Libro(ModeloConFechas):
    titulo = models.CharField(max_length=300)
    isbn = ISBNField(unique=True)
    autores = models.ManyToManyField(Autor, through="Autoria", related_name="libros")
    generos = models.ManyToManyField(Genero, related_name="libros", blank=True)
    publicado = models.DateField(null=True, blank=True)
    paginas = models.PositiveIntegerField(null=True, blank=True)
    sinopsis = models.TextField(blank=True)
    notas = GenericRelation("core.Nota", related_query_name="libro")
    portada = models.ImageField(
        upload_to=ruta_portada,
        blank=True,
        validators=[
            FileExtensionValidator(["jpg", "jpeg", "png", "webp"]),
            TamanoMaximoValidator(2),
        ],
    )
    ficha_pdf = models.FileField(
        upload_to="fichas/%Y/%m/",
        blank=True,
        validators=[FileExtensionValidator(["pdf"]), TamanoMaximoValidator(5), validar_pdf_real],
    )
    metadatos = models.JSONField(default=dict, blank=True)
    etiquetas = ArrayField(models.CharField(max_length=50), default=list, blank=True)
    busqueda = SearchVectorField(null=True, editable=False)
    titulo_busqueda = models.GeneratedField(
        expression=Lower("titulo"),
        output_field=models.CharField(max_length=300),
        db_persist=True,
    )

    objects = LibroQuerySet.as_manager()

    class Meta:
        ordering = ["titulo"]
        indexes = [
            models.Index(fields=["publicado"], name="libro_publicado"),
            GinIndex(fields=["busqueda"], name="libro_busqueda_gin"),
            GinIndex(fields=["metadatos"], name="libro_metadatos_gin"),
        ]

    def __str__(self):
        return self.titulo

    def get_absolute_url(self):
        return reverse("catalogo:detalle_libro", kwargs={"pk": self.pk})


class Autoria(models.Model):
    class Rol(models.TextChoices):
        AUTOR = "autor", "Autor"
        TRADUCTOR = "traductor", "Traductor"
        ILUSTRADOR = "ilustrador", "Ilustrador"

    libro = models.ForeignKey(Libro, on_delete=models.CASCADE)
    autor = models.ForeignKey(Autor, on_delete=models.PROTECT)
    rol = models.CharField(max_length=12, choices=Rol, default=Rol.AUTOR)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["orden"]
        constraints = [
            models.UniqueConstraint(fields=["libro", "autor", "rol"], name="autoria_unica"),
        ]

    def __str__(self):
        return f"{self.autor} ({self.get_rol_display()}) · {self.libro}"


class Ejemplar(ModeloConFechas):
    class Estado(models.TextChoices):
        DISPONIBLE = "disponible", "Disponible"
        PRESTADO = "prestado", "Prestado"
        REPARACION = "reparacion", "En reparación"
        BAJA = "baja", "De baja"

    libro = models.ForeignKey(Libro, on_delete=models.CASCADE, related_name="ejemplares")
    codigo = models.CharField(max_length=20, unique=True)
    estado = models.CharField(max_length=12, choices=Estado, default=Estado.DISPONIBLE)

    class Meta:
        verbose_name_plural = "ejemplares"

    def __str__(self):
        return f"{self.codigo} · {self.libro}"


class Importacion(models.Model):
    """Resumen de una importación en lotes con Celery (módulo 26)."""

    class Estado(models.TextChoices):
        EN_CURSO = "en_curso", "En curso"
        TERMINADA = "terminada", "Terminada"

    estado = models.CharField(max_length=10, choices=Estado, default=Estado.EN_CURSO)
    lotes = models.PositiveIntegerField(default=0)
    creados = models.PositiveIntegerField(default=0)
    existentes = models.PositiveIntegerField(default=0)
    errores = models.JSONField(default=list, blank=True)
    creada = models.DateTimeField(auto_now_add=True)
    terminada = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "importaciones"

    def __str__(self):
        return f"Importación {self.pk} ({self.estado})"
