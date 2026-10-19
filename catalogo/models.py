# catalogo/models.py
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex, OpClass
from django.contrib.postgres.search import SearchVector, SearchVectorField
from django.db import models
from django.db.models import Count, Exists, OuterRef, Q
from django.db.models.functions import Lower
from django.urls import reverse

from core.models import ModeloConFechas

from .fields import ISBNField


class Autor(ModeloConFechas):
    nombre = models.CharField(max_length=200)
    apellidos = models.CharField(max_length=200, blank=True)
    slug = models.SlugField(unique=True)
    biografia = models.TextField(blank=True)
    nacimiento = models.DateField(null=True, blank=True)

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

    VECTOR_BUSQUEDA = SearchVector("titulo", weight="A", config="spanish") + SearchVector(
        "sinopsis", weight="B", config="spanish"
    )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # el vector lo calcula PostgreSQL a partir de las columnas ya guardadas
        type(self).objects.filter(pk=self.pk).update(busqueda=self.VECTOR_BUSQUEDA)


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
