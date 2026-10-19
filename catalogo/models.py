# catalogo/models.py
from django.db import models
from django.db.models.functions import Lower
from django.urls import reverse

from core.models import ModeloConFechas

from .fields import ISBNField


class Autor(ModeloConFechas):
    nombre = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    biografia = models.TextField(blank=True)
    nacimiento = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name_plural = "autores"

    def __str__(self):
        return self.nombre


class Genero(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    padre = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="subgeneros"
    )

    def __str__(self):
        return self.nombre


class Libro(ModeloConFechas):
    titulo = models.CharField(max_length=300)
    isbn = ISBNField(unique=True)
    autores = models.ManyToManyField(Autor, through="Autoria", related_name="libros")
    generos = models.ManyToManyField(Genero, related_name="libros", blank=True)
    publicado = models.DateField(null=True, blank=True)
    paginas = models.PositiveIntegerField(null=True, blank=True)
    sinopsis = models.TextField(blank=True)
    titulo_busqueda = models.GeneratedField(
        expression=Lower("titulo"),
        output_field=models.CharField(max_length=300),
        db_persist=True,
    )

    class Meta:
        ordering = ["titulo"]
        indexes = [models.Index(fields=["publicado"], name="libro_publicado")]

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
