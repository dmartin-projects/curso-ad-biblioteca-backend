# core/middleware.py
import contextvars
import logging
import re
import time
import uuid

from asgiref.sync import iscoroutinefunction, markcoroutinefunction
from django.core.cache import cache
from django.http import JsonResponse

request_id_var = contextvars.ContextVar("request_id", default="-")
ID_VALIDO = re.compile(r"^[A-Za-z0-9-]{1,64}$")
logger = logging.getLogger("rendimiento")


class RequestIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        recibido = request.headers.get("X-Request-ID", "")
        # Viene del cliente: solo si tiene forma de id (si no, inyectaría texto en los logs)
        request_id = recibido if ID_VALIDO.match(recibido) else uuid.uuid4().hex
        request.id = request_id
        token = request_id_var.set(request_id)  # accesible desde los logs (módulo 30)
        try:
            response = self.get_response(request)
        finally:
            request_id_var.reset(token)
        response["X-Request-ID"] = request_id
        return response


class TiempoRespuestaMiddleware:
    async_capable = True
    sync_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        if iscoroutinefunction(self.get_response):
            markcoroutinefunction(self)

    def __call__(self, request):
        if iscoroutinefunction(self):
            return self.__acall__(request)
        inicio = time.perf_counter()
        response = self.get_response(request)
        response["Server-Timing"] = f"app;dur={(time.perf_counter() - inicio) * 1000:.1f}"
        return response

    async def __acall__(self, request):
        inicio = time.perf_counter()
        response = await self.get_response(request)
        response["Server-Timing"] = f"app;dur={(time.perf_counter() - inicio) * 1000:.1f}"
        return response


class MantenimientoMiddleware:
    """Con cache.set("modo_mantenimiento", True), todo responde 503 salvo el admin y la sonda."""

    RUTAS_LIBRES = ("/admin/", "/health/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if cache.get("modo_mantenimiento") and not request.path.startswith(self.RUTAS_LIBRES):
            return JsonResponse(
                {"detail": "En mantenimiento"}, status=503, headers={"Retry-After": "300"}
            )
        return self.get_response(request)


class PeticionesLentasMiddleware:
    UMBRAL_MS = 500

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        inicio = time.perf_counter()
        response = self.get_response(request)
        ms = (time.perf_counter() - inicio) * 1000
        if ms > self.UMBRAL_MS:
            usuario = getattr(request, "user", None)
            logger.warning(
                "Petición lenta %s %s %.0fms usuario=%s id=%s",
                request.method,
                request.path,
                ms,
                usuario.pk if usuario and usuario.is_authenticated else "-",
                getattr(request, "id", "-"),
            )
        return response
