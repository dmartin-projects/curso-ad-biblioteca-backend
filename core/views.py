import json

from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

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
