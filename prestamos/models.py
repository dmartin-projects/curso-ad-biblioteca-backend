# prestamos/models.py
from datetime import timedelta

from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeOperators
from django.db import models
from django.db.models.functions import Now
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import ModeloConFechas


class PrestamoQuerySet(models.QuerySet):
    def activos(self):
        return self.filter(estado=Prestamo.Estado.ACTIVO)

    def vencidos(self):
        return self.activos().filter(fecha_limite__lt=timezone.now())

    def de_socio(self, socio):
        return self.filter(socio=socio)


class PrestamoManager(models.Manager.from_queryset(PrestamoQuerySet)):
    def get_queryset(self):
        return super().get_queryset().select_related("ejemplar__libro", "socio")


class Prestamo(ModeloConFechas):
    class Estado(models.TextChoices):
        ACTIVO = "activo", _("Activo")
        DEVUELTO = "devuelto", _("Devuelto")

    ejemplar = models.ForeignKey(
        "catalogo.Ejemplar",
        on_delete=models.PROTECT,
        related_name="prestamos",
        verbose_name=_("ejemplar"),
    )
    socio = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="prestamos",
        verbose_name=_("socio"),
    )
    fecha_inicio = models.DateTimeField(_("fecha de inicio"), db_default=Now())
    fecha_limite = models.DateTimeField(_("fecha límite"))
    fecha_devolucion = models.DateTimeField(_("fecha de devolución"), null=True, blank=True)
    estado = models.CharField(_("estado"), max_length=10, choices=Estado, default=Estado.ACTIVO)
    notas = GenericRelation("core.Nota", related_query_name="prestamo")

    DURACION = timedelta(days=21)

    objects = PrestamoManager()

    class Meta:
        verbose_name = _("préstamo")
        verbose_name_plural = _("préstamos")
        ordering = ["-fecha_inicio"]
        permissions = [
            ("renovar_prestamo", "Puede renovar préstamos"),
            ("condonar_multa", "Puede condonar multas"),
            ("ver_estadisticas", "Puede ver estadísticas de préstamos"),
        ]
        indexes = [
            models.Index(fields=["socio", "estado"], name="prestamo_socio_estado"),
            models.Index(
                fields=["fecha_limite"],
                name="prestamo_activo_limite",
                condition=models.Q(estado="activo"),
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["ejemplar"],
                condition=models.Q(estado="activo"),
                name="un_prestamo_activo_por_ejemplar",
                violation_error_message="Este ejemplar ya está prestado.",
            ),
            models.CheckConstraint(
                condition=models.Q(fecha_devolucion__isnull=True)
                | models.Q(fecha_devolucion__gte=models.F("fecha_inicio")),
                name="devolucion_posterior_a_inicio",
            ),
        ]

    def __str__(self):
        return f"{self.ejemplar} → {self.socio}"


class Multa(ModeloConFechas):
    prestamo = models.OneToOneField(Prestamo, on_delete=models.CASCADE, related_name="multa")
    importe_base = models.DecimalField(max_digits=8, decimal_places=2)
    recargo = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    total = models.GeneratedField(
        expression=models.F("importe_base") + models.F("recargo"),
        output_field=models.DecimalField(max_digits=9, decimal_places=2),
        db_persist=True,
    )
    pagada = models.BooleanField(default=False)


class PrestamoActivoManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(estado=Prestamo.Estado.ACTIVO)


class PrestamoActivo(Prestamo):
    """Proxy: la misma tabla, solo los activos. En el admin aparece como sección propia."""

    objects = PrestamoActivoManager()

    class Meta:
        proxy = True
        verbose_name = "préstamo activo"
        verbose_name_plural = "préstamos activos"
        ordering = ["fecha_limite"]


class Sala(models.Model):
    nombre = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.nombre


class ReservaSala(models.Model):
    sala = models.ForeignKey(Sala, on_delete=models.CASCADE, related_name="reservas")
    socio = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    periodo = DateTimeRangeField()

    class Meta:
        constraints = [
            ExclusionConstraint(
                name="sin_solapamiento_por_sala",
                expressions=[("sala", RangeOperators.EQUAL), ("periodo", RangeOperators.OVERLAPS)],
                violation_error_message="La sala ya está reservada en ese horario.",
            ),
        ]

    def __str__(self):
        return f"{self.sala} · {self.periodo}"
