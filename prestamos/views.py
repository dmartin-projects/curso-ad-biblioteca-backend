from django.core import signing
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from . import services
from .models import Prestamo

SALT_RENOVACION = "prestamos.renovacion"
VALIDEZ_RENOVACION = 60 * 60 * 24  # 24 horas


def generar_enlace_renovacion(request, prestamo: Prestamo) -> str:
    # la fecha límite va firmada: al renovar cambia y el mismo enlace deja de valer (un solo uso)
    datos = {"p": prestamo.pk, "f": int(prestamo.fecha_limite.timestamp())}
    token = signing.dumps(datos, salt=SALT_RENOVACION)
    return request.build_absolute_uri(reverse("prestamos:renovar", kwargs={"token": token}))


@require_http_methods(["GET", "POST"])
def renovar(request, token):
    """GET muestra qué se renovaría; solo POST renueva.

    Los clientes de correo y los antivirus abren los enlaces para analizarlos: si el GET
    renovase, el préstamo se renovaría sin que el socio lo pidiera.
    """
    try:
        datos = signing.loads(token, salt=SALT_RENOVACION, max_age=VALIDEZ_RENOVACION)
    except signing.SignatureExpired:
        return JsonResponse({"error": "El enlace ha caducado"}, status=410)
    except signing.BadSignature:
        return JsonResponse({"error": "Enlace no válido"}, status=400)
    prestamo = get_object_or_404(Prestamo, pk=datos["p"])
    if int(prestamo.fecha_limite.timestamp()) != datos["f"]:
        return JsonResponse({"error": "Este enlace ya se ha usado"}, status=410)
    if request.method == "GET":  # la página de confirmación lo muestra con un botón
        return JsonResponse(
            {
                "libro": prestamo.ejemplar.libro.titulo,
                "fecha_limite": prestamo.fecha_limite.isoformat(),
                "nueva_fecha_limite": (prestamo.fecha_limite + Prestamo.DURACION).isoformat(),
            }
        )
    try:
        prestamo = services.renovar(prestamo)  # la regla (activo y en plazo) vive en el service
    except services.PrestamoNoRenovable as error:
        return JsonResponse({"error": str(error)}, status=409)
    return JsonResponse({"nueva_fecha_limite": prestamo.fecha_limite.isoformat()})


# ── Módulo 14: permisos globales y por objeto ──
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin  # noqa: E402
from django.views import View  # noqa: E402
from django.views.generic.detail import BaseDetailView, SingleObjectMixin  # noqa: E402
from django.views.generic.list import BaseListView  # noqa: E402


def prestamo_a_dict(p: Prestamo) -> dict:
    return {
        "id": p.pk,
        "libro": p.ejemplar.libro.titulo,
        "socio": str(p.socio),
        "fecha_limite": p.fecha_limite.isoformat(),
        "estado": p.estado,
    }


class PrestamosVisiblesMixin(LoginRequiredMixin):
    """Filtra SIEMPRE por rol: el detalle de un préstamo ajeno da 404 y el listado no lo incluye."""

    raise_exception = True  # API: 403 en vez de redirigir al login

    def get_queryset(self):
        qs = Prestamo.objects.all()  # el manager ya hace select_related (módulo 08)
        if self.request.user.has_perm("prestamos.view_prestamo"):  # bibliotecario: todo
            return qs
        return qs.filter(socio=self.request.user)  # socio: lo suyo


class MisPrestamos(PrestamosVisiblesMixin, BaseListView):
    def render_to_response(self, context):
        return JsonResponse({"results": [prestamo_a_dict(p) for p in context["object_list"]]})


class DetallePrestamo(PrestamosVisiblesMixin, BaseDetailView):
    def render_to_response(self, context):
        return JsonResponse(prestamo_a_dict(context["object"]))


class RenovarPrestamo(LoginRequiredMixin, PermissionRequiredMixin, SingleObjectMixin, View):
    model = Prestamo
    permission_required = "prestamos.renovar_prestamo"
    raise_exception = True
    http_method_names = ["post"]

    def has_permission(self):
        self.object = self.get_object()
        user = self.request.user
        # global (bibliotecario) O sobre el objeto (el propio socio, si sigue activo)
        return user.has_perm(self.permission_required) or user.has_perm(
            self.permission_required, self.object
        )

    def post(self, request, *args, **kwargs):
        try:
            prestamo = services.renovar(self.object)  # la misma regla que el enlace del módulo 13
        except services.PrestamoNoRenovable as error:
            return JsonResponse({"error": str(error)}, status=409)
        return JsonResponse(prestamo_a_dict(prestamo))
