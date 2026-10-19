import json

from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_http_methods

from .models import Autor, Libro


def libro_a_dict(libro: Libro) -> dict:
    return {
        "id": libro.pk,
        "titulo": libro.titulo,
        "isbn": libro.isbn,
        "autor": libro.autor.nombre,
        "publicado": libro.publicado.isoformat() if libro.publicado else None,
    }


@require_GET
def lista_libros(request):
    libros = Libro.objects.select_related("autor").order_by("titulo")
    if q := request.GET.get("q"):
        libros = libros.filter(titulo__icontains=q)
    if autor := request.GET.get("autor"):
        libros = libros.filter(autor__slug=autor)
    if desde := request.GET.get("desde"):
        if desde.isdigit():
            libros = libros.filter(publicado__year__gte=int(desde))
    pagina = Paginator(libros, 20).get_page(request.GET.get("page"))
    return JsonResponse(
        {
            "count": pagina.paginator.count,
            "page": pagina.number,
            "results": [libro_a_dict(libro) for libro in pagina],
        }
    )


@require_http_methods(["GET", "PATCH", "DELETE"])
def detalle_libro(request, pk):
    libro = get_object_or_404(Libro.objects.select_related("autor"), pk=pk)

    if request.method == "GET":
        return JsonResponse(libro_a_dict(libro))

    # leer es público; cambiar o borrar exige el permission de ese verbo (anónimo incluido → 403)
    permiso = "catalogo.change_libro" if request.method == "PATCH" else "catalogo.delete_libro"
    if not request.user.has_perm(permiso):
        raise PermissionDenied

    if request.method == "PATCH":
        try:
            datos = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "JSON inválido"}, status=400)
        if "titulo" in datos:
            libro.titulo = datos["titulo"]
            libro.save(update_fields=["titulo"])
        return JsonResponse(libro_a_dict(libro))

    libro.delete()
    return HttpResponse(status=204)


@require_GET
def detalle_autor(request, slug):
    autor = get_object_or_404(Autor.objects.prefetch_related("libros"), slug=slug)
    return JsonResponse(
        {
            "id": autor.pk,
            "nombre": autor.nombre,
            "libros": [{"id": libro.pk, "titulo": libro.titulo} for libro in autor.libros.all()],
        }
    )


@require_GET
def libro_por_isbn(request, isbn):
    return JsonResponse(libro_a_dict(get_object_or_404(Libro, isbn=isbn)))


@require_GET
def libros_por_anio(request, anio):
    libros = Libro.objects.select_related("autor").filter(publicado__year=anio)
    return JsonResponse([libro_a_dict(libro) for libro in libros], safe=False)


# ── Módulo 04: las mismas vistas como CBV ──
import csv  # noqa: E402

from django.views.generic.detail import BaseDetailView  # noqa: E402
from django.views.generic.list import BaseListView  # noqa: E402

from .mixins import FiltrosLibroMixin, JSONResponseMixin  # noqa: E402


class LibroListJSON(JSONResponseMixin, FiltrosLibroMixin, BaseListView):
    paginate_by = 20

    def get_data(self, context):
        return {
            "count": context["paginator"].count,
            "page": context["page_obj"].number,
            "results": [libro_a_dict(libro) for libro in context["object_list"]],
        }


class AutorDetailJSON(JSONResponseMixin, BaseDetailView):
    model = Autor  # busca por slug porque la URL trae <slug:slug> (slug_url_kwarg = "slug")

    def get_queryset(self):
        return super().get_queryset().prefetch_related("libros")

    def get_data(self, context):
        autor = context["object"]
        return {
            "id": autor.pk,
            "nombre": autor.nombre,
            "libros": [{"id": libro.pk, "titulo": libro.titulo} for libro in autor.libros.all()],
        }


class ExportarLibrosCSV(FiltrosLibroMixin, BaseListView):
    def render_to_response(self, context, **response_kwargs):
        respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
        respuesta["Content-Disposition"] = 'attachment; filename="libros.csv"'
        writer = csv.writer(respuesta)
        writer.writerow(["id", "titulo", "isbn", "autor"])
        for libro in context["object_list"]:
            writer.writerow([libro.pk, libro.titulo, libro.isbn, libro.autor.nombre])
        return respuesta


# ── Módulo 05: validar JSON con un formulario ──
from django.contrib.auth.decorators import permission_required  # noqa: E402
from django.views.decorators.http import require_POST  # noqa: E402

from .forms import LibroForm  # noqa: E402


@permission_required("catalogo.add_libro", raise_exception=True)
@require_POST
def crear_libro(request):
    try:
        datos = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON inválido"}, status=400)

    form = LibroForm(data=datos)
    if not form.is_valid():
        return JsonResponse({"errores": form.errors.get_json_data()}, status=400)

    libro = form.save()
    return JsonResponse(libro_a_dict(libro), status=201)
