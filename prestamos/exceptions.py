# prestamos/exceptions.py (módulo 38)
from django.utils.translation import gettext_lazy as _

from core.exceptions import ErrorDeDominio


class EjemplarNoDisponible(ErrorDeDominio):
    codigo = "ejemplar_no_disponible"
    mensaje = _("El ejemplar no está disponible.")


class PrestamoYaDevuelto(ErrorDeDominio):
    codigo = "prestamo_ya_devuelto"
    mensaje = _("El préstamo ya estaba devuelto.")


class PrestamoNoRenovable(ErrorDeDominio):
    codigo = "prestamo_no_renovable"
    mensaje = _("Este préstamo no se puede renovar.")


class LimitePrestamosAlcanzado(ErrorDeDominio):
    codigo = "limite_prestamos"
    status = 422  # la petición es válida, pero la regla del socio la rechaza
    mensaje = _("Has alcanzado el máximo de préstamos activos.")
