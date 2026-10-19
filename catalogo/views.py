import json
from urllib.parse import urlencode

from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_http_methods

from core.cache import obtener_version

from .models import Autor, Libro


def libro_a_dict(libro: Libro) -> dict:
    return {
        "id": libro.pk,
        "titulo": libro.titulo,
        "isbn": libro.isbn,
        "autores": [autor.nombre for autor in libro.autores.all()],
        "publicado": libro.publicado.isoformat() if libro.publicado else None,
    }


@require_GET
def lista_libros(request):
    libros = Libro.objects.para_listado().order_by("titulo")
    if q := request.GET.get("q"):
        libros = libros.buscar(q)
    if autor := request.GET.get("autor"):
        libros = libros.de_autor(autor)
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
    libro = get_object_or_404(Libro.objects.prefetch_related("autores"), pk=pk)

    if request.method == "GET":
        registrar_visto(request, libro.pk)
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
    libros = Libro.objects.prefetch_related("autores").filter(publicado__year=anio)
    return JsonResponse([libro_a_dict(libro) for libro in libros], safe=False)


# ── Módulo 04: las mismas vistas como CBV ──
import csv  # noqa: E402

from django.views.generic.detail import BaseDetailView  # noqa: E402
from django.views.generic.list import BaseListView  # noqa: E402

from .mixins import FiltrosLibroMixin, JSONResponseMixin  # noqa: E402


class LibroListJSON(JSONResponseMixin, FiltrosLibroMixin, BaseListView):
    paginate_by = 20

    def get(self, request, *args, **kwargs):
        # módulo 23: caché versionada; la clave incluye TODO lo que cambia el resultado
        filtros = urlencode(sorted(request.GET.items()))
        clave = f"catalogo:v{obtener_version('catalogo')}:libros:{filtros}"
        datos = cache.get(clave)
        if datos is None:
            self.object_list = self.get_queryset()
            datos = self.get_data(self.get_context_data())
            cache.set(clave, datos, timeout=600)
        return JsonResponse(datos)

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
        writer.writerow(["id", "titulo", "isbn", "autores"])
        for libro in context["object_list"]:
            autores = "; ".join(autor.nombre for autor in libro.autores.all())
            writer.writerow([libro.pk, libro.titulo, libro.isbn, autores])
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


# ── Módulo 11: búsqueda de texto completo y autocompletado tolerante a erratas ──
import unicodedata  # noqa: E402

from django.contrib.postgres.lookups import Unaccent  # noqa: E402
from django.contrib.postgres.search import (  # noqa: E402
    SearchHeadline,
    SearchQuery,
    SearchRank,
    TrigramWordSimilarity,
)
from django.db.models import F  # noqa: E402


@require_GET
def buscar_libros(request):
    texto = request.GET.get("q", "").strip()
    if not texto:
        return JsonResponse({"results": []})
    consulta = SearchQuery(texto, config="spanish", search_type="websearch")
    libros = (
        Libro.objects.filter(busqueda=consulta)  # usa el índice GIN
        .annotate(
            relevancia=SearchRank(F("busqueda"), consulta),
            fragmento=SearchHeadline("sinopsis", consulta, config="spanish", max_words=20),
        )
        .order_by("-relevancia", "titulo")[:20]
    )
    return JsonResponse(
        {
            "results": [
                {"id": libro.pk, "titulo": libro.titulo, "fragmento": libro.fragmento}
                for libro in libros
            ]
        }
    )


def sin_acentos(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )


@require_GET
def autocompletar_autores(request):
    q = sin_acentos(request.GET.get("q", "").strip())
    if len(q) < 2:
        return JsonResponse({"results": []})
    autores = (
        Autor.objects.annotate(similitud=TrigramWordSimilarity(q, Unaccent("nombre")))
        .filter(similitud__gt=0.3)
        .order_by("-similitud")[:10]
    )
    return JsonResponse({"results": [{"id": a.pk, "nombre": a.nombre} for a in autores]})


# ── Módulo 13: "vistos recientemente" en la sesión ──
MAX_VISTOS = 5


def registrar_visto(request, pk: int) -> None:
    vistos = [v for v in request.session.get("vistos", []) if v != pk]
    request.session["vistos"] = [pk, *vistos][:MAX_VISTOS]  # reasignar: Django marca la sesión


@require_GET
def recientes(request):
    ids = request.session.get("vistos", [])
    por_id = Libro.objects.prefetch_related("autores").in_bulk(ids)
    # en el orden de la sesión (el más reciente primero); los borrados desaparecen solos
    return JsonResponse({"results": [libro_a_dict(por_id[pk]) for pk in ids if pk in por_id]})
