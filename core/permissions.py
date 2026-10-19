# core/permissions.py — permisos de la API reutilizables (módulo 36)
from django.utils.translation import gettext_lazy as _
from rest_framework.permissions import SAFE_METHODS, BasePermission

GRUPOS_PERSONAL = ("bibliotecarios", "responsables")


def es_personal(usuario) -> bool:
    """Personal de la biblioteca. Se cachea en el objeto usuario: una consulta por petición, no por
    cada vez que se pregunta (un permiso de vista y otro de objeto preguntarían dos veces)."""
    if not (usuario and usuario.is_authenticated):
        return False
    if not hasattr(usuario, "_es_personal"):
        usuario._es_personal = (
            usuario.is_staff
            or usuario.is_superuser
            or usuario.groups.filter(name__in=GRUPOS_PERSONAL).exists()
        )
    return usuario._es_personal


class EsBibliotecario(BasePermission):
    message = _("Solo el personal de la biblioteca puede hacer esto.")

    def has_permission(self, request, view):
        return es_personal(request.user)


class SoloLectura(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS
