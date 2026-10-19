# prestamos/models.py
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models.functions import Now

from core.models import ModeloConFechas


class Prestamo(ModeloConFechas):
    class Estado(models.TextChoices):
        ACTIVO = "activo", "Activo"
        DEVUELTO = "devuelto", "Devuelto"

    ejemplar = models.ForeignKey(
        "catalogo.Ejemplar", on_delete=models.PROTECT, related_name="prestamos"
    )
    socio = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="prestamos"
    )
    fecha_inicio = models.DateTimeField(db_default=Now())
    fecha_limite = models.DateTimeField()
    fecha_devolucion = models.DateTimeField(null=True, blank=True)
    estado = models.CharField(max_length=10, choices=Estado, default=Estado.ACTIVO)

    DURACION = timedelta(days=21)

    class Meta:
        ordering = ["-fecha_inicio"]
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
