# prestamos/api/views.py
import csv

from django.http import StreamingHttpResponse
from django.utils.translation import gettext_lazy as _
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response

from catalogo.archivos import Eco
from core.api.serializers import ProblemaSerializer
from core.pagination import PaginacionCursorPrestamos
from core.permissions import EsBibliotecario, es_personal
from prestamos import services
from prestamos.models import Prestamo

from .filters import PrestamoFilter
from .serializers import PrestamoSerializer, PrestarSerializer


def prestamos_visibles(user):
    """El socio, los suyos; el personal, todos (la regla del módulo 14)."""
    qs = Prestamo.objects.all()
    return qs if es_personal(user) else qs.filter(socio=user)


class EsSocioDelPrestamoOBibliotecario(BasePermission):
    message = _("Solo el socio del préstamo o el personal pueden hacer esto.")

    def has_object_permission(self, request, view, prestamo):
        return prestamo.socio_id == request.user.id or es_personal(request.user)


class PrestamoViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Sin update ni destroy: un préstamo cambia solo con acciones de negocio."""

    serializer_class = PrestamoSerializer
    queryset = Prestamo.objects.none()  # solo para el esquema OpenAPI: el real es get_queryset()
    pagination_class = PaginacionCursorPrestamos  # módulo 37: historial con scroll infinito
    filter_backends = [DjangoFilterBackend]  # el orden lo fija el cursor (sin ?ordering=)
    filterset_class = PrestamoFilter

    def get_permissions(self):
        if self.action == "vencidos":
            return [EsBibliotecario()]
        if self.action in ("devolver", "renovar"):
            # get_queryset ya deja fuera lo ajeno (404); esto es la segunda capa
            return [IsAuthenticated(), EsSocioDelPrestamoOBibliotecario()]
        return [IsAuthenticated()]

    def get_queryset(self):
        return prestamos_visibles(self.request.user).select_related(
            "ejemplar__libro", "multa"
        )  # sin order_by: lo pone PaginacionCursorPrestamos

    @extend_schema(
        request=PrestarSerializer,
        responses={
            201: PrestamoSerializer,
            400: ProblemaSerializer,
            409: ProblemaSerializer,
            422: ProblemaSerializer,
        },
    )
    def create(self, request, *args, **kwargs):  # POST /prestamos/ → servicio
        entrada = PrestarSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        # EjemplarNoDisponible → 409 con su código: lo traduce el exception handler (módulo 38)
        prestamo = services.prestar(entrada.validated_data["ejemplar_id"], request.user)
        prestamo = self.get_queryset().get(pk=prestamo.pk)  # fecha_inicio la pone la BD
        return Response(self.get_serializer(prestamo).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses={200: PrestamoSerializer, 409: ProblemaSerializer})
    @action(detail=True, methods=["post"])  # POST /prestamos/{pk}/devolver/
    def devolver(self, request, pk=None, **kwargs):
        prestamo = services.devolver(self.get_object())  # PrestamoYaDevuelto → 409
        return Response(self.get_serializer(prestamo).data)

    @extend_schema(request=None, responses={200: PrestamoSerializer, 409: ProblemaSerializer})
    @action(detail=True, methods=["post"])  # POST /prestamos/{pk}/renovar/
    def renovar(self, request, pk=None, **kwargs):
        prestamo = services.renovar(self.get_object())  # PrestamoNoRenovable → 409
        return Response(self.get_serializer(prestamo).data)

    @extend_schema(responses={(200, "text/csv"): OpenApiTypes.STR})
    @action(detail=False, methods=["get"])  # GET /prestamos/exportar/?estado=…&desde=…
    def exportar(self, request, **kwargs):
        """CSV en streaming con los MISMOS filtros que el listado: exportas lo que ves."""
        filas = (
            self.filter_queryset(self.get_queryset())
            .order_by("-fecha_inicio", "-id")
            .values_list("id", "ejemplar__libro__titulo", "socio__email", "fecha_inicio", "estado")
            .iterator(chunk_size=2000)  # memoria constante aunque sean 500.000
        )
        escritor = csv.writer(Eco(), delimiter=";")

        def generar():
            yield escritor.writerow(["id", "libro", "socio", "inicio", "estado"])
            for pk, titulo, email, inicio, estado in filas:
                yield escritor.writerow([pk, titulo, email, inicio.isoformat(), estado])

        response = StreamingHttpResponse(generar(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="prestamos.csv"'
        return response

    @action(detail=False, methods=["get"])  # GET /prestamos/vencidos/
    def vencidos(self, request, **kwargs):
        qs = self.filter_queryset(self.get_queryset().vencidos())
        pagina = self.paginate_queryset(qs)
        if pagina is None:  # sin paginación configurada (llega en el módulo 37)
            return Response(self.get_serializer(qs, many=True).data)
        return self.get_paginated_response(self.get_serializer(pagina, many=True).data)
