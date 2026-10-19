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
