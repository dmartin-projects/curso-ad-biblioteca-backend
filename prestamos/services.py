# prestamos/services.py
from django.db import transaction
from django.db.models import DecimalField, Prefetch, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from catalogo.models import Ejemplar
from usuarios.models import PerfilSocio, Usuario

from .models import Prestamo
from .tasks import enviar_confirmacion_prestamo


class EjemplarNoDisponible(Exception):
    pass


class LimitePrestamosAlcanzado(Exception):
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
    # módulo 15: el perfil, bloqueado; dos préstamos a la vez del mismo socio no pasan los dos el límite
    perfil = PerfilSocio.objects.select_for_update().get(usuario=socio)
    if Prestamo.objects.activos().filter(socio=socio).count() >= perfil.max_prestamos:
        raise LimitePrestamosAlcanzado(
            f"Ya tienes {perfil.max_prestamos} préstamos activos, el máximo."
        )
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

    # módulo 26: el email sale en segundo plano, y solo si el préstamo llega a confirmarse
    transaction.on_commit(lambda: enviar_confirmacion_prestamo.enqueue(prestamo.pk))
    return prestamo


# ── Módulo 15: los servicios emiten eventos de dominio ──
from .signals import prestamo_devuelto, prestamo_vencido  # noqa: E402


@transaction.atomic
def devolver(prestamo: Prestamo) -> Prestamo:
    prestamo.estado = Prestamo.Estado.DEVUELTO
    prestamo.fecha_devolucion = timezone.now()
    prestamo.save(update_fields=["estado", "fecha_devolucion"])
    # save() y no update(): así el ejemplar envía post_save, como cualquier otro cambio
    ejemplar = prestamo.ejemplar
    ejemplar.estado = Ejemplar.Estado.DISPONIBLE
    ejemplar.save(update_fields=["estado"])
    prestamo_devuelto.send(sender=Prestamo, prestamo=prestamo)
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


def avisar_vencidos() -> int:
    """Emite prestamo_vencido por cada préstamo activo fuera de plazo (lo lanzará Celery Beat, módulo 26)."""
    ahora = timezone.now()
    vencidos = Prestamo.objects.vencidos()
    for prestamo in vencidos:
        dias = (ahora - prestamo.fecha_limite).days
        prestamo_vencido.send(sender=Prestamo, prestamo=prestamo, dias_retraso=dias)
    return len(vencidos)


# Por qué la fecha límite NO va en una signal pre_save de Prestamo:
# - es la regla central del caso de uso "prestar": quien lea prestar() debe verla ahí, no descubrir
#   que un receptor en otro archivo la rellena;
# - una signal no se ejecuta con bulk_create() ni con update(): un préstamo creado así quedaría sin
#   fecha límite (y la columna es NOT NULL: fallaría de forma poco clara);
# - depende del socio (max_prestamos, tipo de carné…) y del contexto, cosas que conoce el servicio.
