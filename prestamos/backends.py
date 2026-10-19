# prestamos/backends.py
from .models import Prestamo


class PrestamoPermisosBackend:
    """Permisos por objeto sobre préstamos. No autentica: solo autoriza."""

    def authenticate(self, request, **kwargs):
        return None

    def has_perm(self, user_obj, perm, obj=None):
        if obj is None or not user_obj.is_active:
            return False
        if isinstance(obj, Prestamo):
            if perm == "prestamos.view_prestamo":
                return obj.socio_id == user_obj.pk
            if perm == "prestamos.renovar_prestamo":
                return obj.socio_id == user_obj.pk and obj.estado == Prestamo.Estado.ACTIVO
        return False
