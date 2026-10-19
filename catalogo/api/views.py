# catalogo/api/views.py
from django.db.models import Count, Q
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from catalogo.models import Ejemplar, Libro


class EstadisticasSerializer(serializers.Serializer):
    """Solo documenta la respuesta (drf-spectacular no puede deducirla de un aggregate)."""

    libros = serializers.IntegerField()
    con_ejemplares_disponibles = serializers.IntegerField()


def _estadisticas() -> dict:
    return Libro.objects.aggregate(
        libros=Count("id", distinct=True),  # el JOIN con ejemplares repite cada libro
        con_ejemplares_disponibles=Count(
            "id", filter=Q(ejemplares__estado=Ejemplar.Estado.DISPONIBLE), distinct=True
        ),
    )


@extend_schema(responses=EstadisticasSerializer)
@api_view(["GET"])
@permission_classes([AllowAny])  # pública: lo declara explícitamente
def estadisticas_catalogo(request, version):
    return Response(_estadisticas())


class EstadisticasCatalogo(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses=EstadisticasSerializer)
    def get(self, request, version):
        return Response(_estadisticas())


# ── módulo 34: ViewSets ──
from pathlib import Path  # noqa: E402

from django.http import FileResponse  # noqa: E402
from django.shortcuts import redirect  # noqa: E402
from django.utils.translation import gettext as _  # noqa: E402
from rest_framework import viewsets  # noqa: E402
from rest_framework.decorators import action  # noqa: E402
from rest_framework.exceptions import NotFound  # noqa: E402
from rest_framework.filters import OrderingFilter, UnaccentedSearchFilter  # noqa: E402
from rest_framework.parsers import MultiPartParser  # noqa: E402
from rest_framework.permissions import DjangoModelPermissions, IsAuthenticated  # noqa: E402
from storages.backends.s3 import S3Storage  # noqa: E402

from catalogo.models import Autor, Genero  # noqa: E402
from core.permissions import EsBibliotecario, SoloLectura  # noqa: E402

from .filters import LibroFilter  # noqa: E402
from .serializers import (  # noqa: E402
    AutorSerializer,
    GeneroSerializer,
    LibroListaSerializer,
    LibroSerializer,
    PortadaSerializer,
)

# módulo 36: cualquiera autenticado lee; solo el personal escribe
LECTURA_O_PERSONAL = [IsAuthenticated & (SoloLectura | EsBibliotecario)]


class LibroViewSet(viewsets.ModelViewSet):
    permission_classes = LECTURA_O_PERSONAL  # (en el módulo 34: DjangoModelPermissions)
    queryset = Libro.objects.none()  # para el esquema OpenAPI
    filterset_class = LibroFilter  # módulo 37
    search_fields = ["titulo", "=isbn", "autores__nombre"]
    ordering_fields = [
        "titulo",
        "publicado",
        "paginas",
        "ejemplares_disponibles",
    ]  # 🔐 lista blanca
    ordering = ["titulo", "id"]  # el id desempata: paginación estable

    def get_queryset(self):
        qs = Libro.objects.prefetch_related("autores", "generos")
        if self.action == "list":
            qs = qs.con_disponibles()  # la anotación solo donde se usa
        return qs

    def get_serializer_class(self):
        if self.action == "list":
            return LibroListaSerializer
        if self.action == "portada":
            return PortadaSerializer
        return LibroSerializer

    @action(detail=True, methods=["get", "put"], parser_classes=[MultiPartParser])
    def portada(self, request, pk=None, **kwargs):
        """GET descarga la portada; PUT (multipart, solo personal) la sustituye. Módulo 38."""
        libro = self.get_object()  # get_queryset + permisos (PUT no es SAFE → EsBibliotecario)
        if request.method == "PUT":
            serializer = self.get_serializer(libro, data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save()  # la signal del módulo 20 borra la antigua al confirmar
            return Response(serializer.data)
        if not libro.portada:
            raise NotFound(_("Este libro no tiene portada."))
        if isinstance(libro.portada.storage, S3Storage):
            return redirect(libro.portada.url)  # URL firmada de 5 minutos (módulo 20)
        return FileResponse(libro.portada.open("rb"), filename=Path(libro.portada.name).name)

    # destroy: si tiene préstamos, ProtectedError → 409 "en_uso" (exception handler, módulo 38)


class AutorViewSet(viewsets.ModelViewSet):
    permission_classes = LECTURA_O_PERSONAL
    queryset = Autor.objects.all()
    serializer_class = AutorSerializer
    lookup_field = "slug"  # /autores/frank-herbert/
    # módulo 37: "garcia" encuentra "García" (necesita la extensión unaccent, módulo 11)
    filter_backends = [UnaccentedSearchFilter, OrderingFilter]
    search_fields = ["nombre", "apellidos"]
    ordering_fields = ["nombre"]
    ordering = ["nombre", "id"]

    def perform_create(self, serializer):
        from django.utils.text import slugify

        serializer.save(slug=slugify(serializer.validated_data["nombre"]))


class GeneroViewSet(viewsets.ModelViewSet):
    """Permisos de modelo de Django: se gestionan desde el admin asignando grupos (módulo 36)."""

    permission_classes = [DjangoModelPermissions]
    queryset = Genero.objects.select_related("padre").order_by("nombre")
    serializer_class = GeneroSerializer
    pagination_class = None  # lista corta y acotada
