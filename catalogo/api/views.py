# catalogo/api/views.py
from django.db.models import Count, Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from catalogo.models import Ejemplar, Libro


def _estadisticas() -> dict:
    return Libro.objects.aggregate(
        libros=Count("id", distinct=True),  # el JOIN con ejemplares repite cada libro
        con_ejemplares_disponibles=Count(
            "id", filter=Q(ejemplares__estado=Ejemplar.Estado.DISPONIBLE), distinct=True
        ),
    )


@api_view(["GET"])
@permission_classes([AllowAny])  # pública: lo declara explícitamente
def estadisticas_catalogo(request, version):
    return Response(_estadisticas())


class EstadisticasCatalogo(APIView):
    permission_classes = [AllowAny]

    def get(self, request, version):
        return Response(_estadisticas())


# ── módulo 34: ViewSets ──
from django.db.models import ProtectedError  # noqa: E402
from django.utils.translation import gettext as _  # noqa: E402
from rest_framework import status, viewsets  # noqa: E402
from rest_framework.permissions import DjangoModelPermissions  # noqa: E402

from catalogo.models import Autor  # noqa: E402

from .serializers import AutorSerializer, LibroListaSerializer, LibroSerializer  # noqa: E402


class LibroViewSet(viewsets.ModelViewSet):
    # Leer: cualquier usuario autenticado. Crear/editar/borrar: quien tenga add/change/delete_libro
    # (los bibliotecarios). Sin esto, cualquier socio podría borrar el catálogo. Más en el módulo 36.
    permission_classes = [DjangoModelPermissions]
    queryset = Libro.objects.none()  # DjangoModelPermissions lo usa para saber el modelo

    def get_queryset(self):
        qs = Libro.objects.prefetch_related("autores", "generos")
        if self.action == "list":
            qs = qs.con_disponibles()  # la anotación solo donde se usa
        return qs.order_by("titulo")

    def get_serializer_class(self):
        return LibroListaSerializer if self.action == "list" else LibroSerializer

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:  # tiene ejemplares con préstamos: la BD lo impide (PROTECT)
            return Response(
                {"detail": _("El libro tiene préstamos registrados y no se puede borrar.")},
                status=status.HTTP_409_CONFLICT,
            )


class AutorViewSet(viewsets.ModelViewSet):
    permission_classes = [DjangoModelPermissions]
    queryset = Autor.objects.order_by("nombre")
    serializer_class = AutorSerializer
    lookup_field = "slug"  # /autores/frank-herbert/

    def perform_create(self, serializer):
        from django.utils.text import slugify

        serializer.save(slug=slugify(serializer.validated_data["nombre"]))
