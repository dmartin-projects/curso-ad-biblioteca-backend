# prestamos/eventos.py — Server-Sent Events (módulo 24)
import asyncio
import json

from django.http import JsonResponse, StreamingHttpResponse

from .models import Prestamo


async def eventos_prestamos(request, intervalo: float = 10):
    usuario = await request.auser()
    if not usuario.is_authenticated:
        return JsonResponse({"error": "Inicia sesión"}, status=401)

    async def flujo():
        while True:
            n = await Prestamo.objects.filter(socio=usuario, estado="activo").acount()
            yield f"data: {json.dumps({'activos': n})}\n\n"
            await asyncio.sleep(intervalo)

    return StreamingHttpResponse(
        flujo(),
        content_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},  # sin búfer en nginx
    )
