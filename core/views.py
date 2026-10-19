import json
import logging

from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from .models import Nota

PERMITIDOS = {("catalogo", "libro"), ("catalogo", "autor"), ("prestamos", "prestamo")}


def objetos_visibles(request, modelo):
    """Lo que el usuario puede ver de ese modelo: los préstamos, solo los suyos (módulo 14)."""
    qs = modelo._default_manager.all()
    if modelo._meta.label_lower == "prestamos.prestamo" and not request.user.has_perm(
        "prestamos.view_prestamo"
    ):
        qs = qs.filter(socio=request.user)
    return qs


def nota_a_dict(nota: Nota) -> dict:
    return {
        "id": nota.pk,
        "texto": nota.texto,
        "usuario": str(nota.usuario),
        "creada": nota.creada.isoformat(),
    }


@login_required
@require_http_methods(["GET", "POST"])
def notas(request, app, modelo, pk):
    if (app, modelo) not in PERMITIDOS:
        raise Http404
    ct = get_object_or_404(ContentType, app_label=app, model=modelo)
    objeto = get_object_or_404(objetos_visibles(request, ct.model_class()), pk=pk)

    if request.method == "POST":
        try:
            texto = json.loads(request.body).get("texto", "").strip()
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({"error": "JSON inválido"}, status=400)
        if not texto:
            return JsonResponse({"errores": {"texto": ["Obligatorio."]}}, status=400)
        nota = Nota.objects.create(objeto=objeto, usuario=request.user, texto=texto)
        return JsonResponse(nota_a_dict(nota), status=201)

    lista = Nota.objects.filter(content_type=ct, object_id=objeto.pk).select_related("usuario")
    return JsonResponse({"results": [nota_a_dict(n) for n in lista]})


def ultimas_notas() -> list[dict]:
    """Las 20 últimas notas con su objeto: 1 consulta + 1 por cada TIPO de objeto (no por nota)."""
    lista = Nota.objects.select_related("content_type")[:20].prefetch_related("objeto")
    return [{"texto": n.texto, "sobre": str(n.objeto), "tipo": n.content_type.model} for n in lista]


# ── módulo 29: informes de violaciones de CSP ──
csp_logger = logging.getLogger("seguridad.csp")


@csrf_exempt  # ✅ justificado: lo envía el navegador sin token; no usa la sesión ni cambia nada
@require_POST
def csp_report(request):
    try:
        informe = json.loads(request.body or b"{}").get("csp-report", {})
    except json.JSONDecodeError:
        return HttpResponse(status=400)
    csp_logger.warning(
        "CSP: %s bloqueó %s en %s",
        informe.get("violated-directive") or informe.get("effective-directive"),
        informe.get("blocked-uri"),
        informe.get("document-uri"),
    )
    return HttpResponse(status=204)


# ── módulo 30: health checks ──
from django.core.cache import cache  # noqa: E402
from django.db import connection  # noqa: E402


def health_live(request):  # ¿el proceso responde? (no toca nada más)
    return JsonResponse({"ok": True})


def health_ready(request):  # ¿puede atender? (BD y caché)
    estado = {}
    try:
        with connection.cursor() as c:
            c.execute("SELECT 1")
        estado["db"] = "ok"
    except Exception:
        estado["db"] = "error"
    try:
        cache.set("health", 1, 5)
        estado["cache"] = "ok" if cache.get("health") == 1 else "error"
    except Exception:
        estado["cache"] = "error"
    ok = all(v == "ok" for v in estado.values())
    return JsonResponse(estado, status=200 if ok else 503)
