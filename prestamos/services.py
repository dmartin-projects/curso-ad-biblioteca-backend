# prestamos/services.py
from django.db import transaction
from django.db.models import DecimalField, Prefetch, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from catalogo.models import Ejemplar
from usuarios.models import Usuario

from .models import Prestamo


class EjemplarNoDisponible(Exception):
    pass


def informe_socios():
    socios = Usuario.objects.annotate(
        multas_pendientes=Coalesce(
            Sum("prestamos__multa__total", filter=Q(prestamos__multa__pagada=False)),
            Value(0),
            output_field=DecimalField(),
        ),
    ).prefetch_related(
        Prefetch(
            "prestamos",
            queryset=Prestamo.objects.filter(estado="activo").select_related("ejemplar__libro"),
            to_attr="activos",
        )
    )
    return [
        {
            "socio": s.email,
            "activos": [(p.ejemplar.libro.titulo, p.fecha_limite) for p in s.activos],
            "multas_pendientes": s.multas_pendientes,
        }
        for s in socios
    ]  # 2 consultas, tengas 10 o 10.000 socios


@transaction.atomic
def prestar(ejemplar_id: int, socio) -> Prestamo:
    ejemplar = Ejemplar.objects.select_for_update().get(pk=ejemplar_id)
    if ejemplar.estado != Ejemplar.Estado.DISPONIBLE:
        raise EjemplarNoDisponible(f"El ejemplar {ejemplar.codigo} no está disponible")

    prestamo = Prestamo.objects.create(
        ejemplar=ejemplar,
        socio=socio,
        fecha_limite=timezone.now() + Prestamo.DURACION,
    )
    ejemplar.estado = Ejemplar.Estado.PRESTADO
    ejemplar.save(update_fields=["estado"])

    transaction.on_commit(lambda: print(f"Préstamo {prestamo.pk} confirmado"))
    return prestamo


class PrestamoNoRenovable(Exception):
    pass


@transaction.atomic
def renovar(prestamo: Prestamo) -> Prestamo:
    """Amplía el plazo DURACION días. Solo préstamos activos y que aún no han vencido."""
    prestamo = Prestamo.objects.select_for_update().get(pk=prestamo.pk)
    if prestamo.estado != Prestamo.Estado.ACTIVO:
        raise PrestamoNoRenovable("Solo se renuevan préstamos activos.")
    if prestamo.fecha_limite < timezone.now():
        raise PrestamoNoRenovable("Un préstamo vencido no se renueva: devuélvelo.")
    prestamo.fecha_limite += Prestamo.DURACION
    prestamo.save(update_fields=["fecha_limite"])
    return prestamo
