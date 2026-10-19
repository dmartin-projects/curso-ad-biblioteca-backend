# prestamos/api/views.py
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response

from catalogo.models import Ejemplar
from core.permissions import EsBibliotecario, es_personal
from prestamos import services
from prestamos.models import Prestamo

from .serializers import PrestamoSerializer, PrestarSerializer


def prestamos_visibles(user):
    """El socio, los suyos; el personal, todos (la regla del módulo 14)."""
    qs = Prestamo.objects.all()
    return qs if es_personal(user) else qs.filter(socio=user)


class EsSocioDelPrestamoOBibliotecario(BasePermission):
    message = gettext_lazy("Solo el socio del préstamo o el personal pueden hacer esto.")

    def has_object_permission(self, request, view, prestamo):
        return prestamo.socio_id == request.user.id or es_personal(request.user)


def conflicto(error: Exception) -> Response:
    return Response({"detail": str(error)}, status=status.HTTP_409_CONFLICT)


class PrestamoViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Sin update ni destroy: un préstamo cambia solo con acciones de negocio."""

    serializer_class = PrestamoSerializer
    queryset = Prestamo.objects.none()  # solo para el esquema OpenAPI: el real es get_queryset()

    def get_permissions(self):
        if self.action == "vencidos":
            return [EsBibliotecario()]
        if self.action in ("devolver", "renovar"):
            # get_queryset ya deja fuera lo ajeno (404); esto es la segunda capa
            return [IsAuthenticated(), EsSocioDelPrestamoOBibliotecario()]
        return [IsAuthenticated()]

    def get_queryset(self):
        return (
            prestamos_visibles(self.request.user)
            .select_related("ejemplar__libro", "multa")
            .order_by("-fecha_inicio")
        )

    def create(self, request, *args, **kwargs):  # POST /prestamos/ → servicio
        entrada = PrestarSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            prestamo = services.prestar(entrada.validated_data["ejemplar_id"], request.user)
        except Ejemplar.DoesNotExist:
            return Response(
                {"ejemplar_id": [_("No existe ese ejemplar.")]}, status=status.HTTP_400_BAD_REQUEST
            )
        except services.EjemplarNoDisponible as error:
            return conflicto(error)
        except services.LimitePrestamosAlcanzado as error:  # el máximo del perfil (módulo 15)
            return Response({"detail": str(error)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        prestamo = self.get_queryset().get(pk=prestamo.pk)  # fecha_inicio la pone la BD
        return Response(self.get_serializer(prestamo).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])  # POST /prestamos/{pk}/devolver/
    def devolver(self, request, pk=None, **kwargs):
        try:
            prestamo = services.devolver(self.get_object())  # get_object: ajeno → 404
        except services.PrestamoYaDevuelto:
            return conflicto(_("El préstamo ya estaba devuelto."))
        return Response(self.get_serializer(prestamo).data)

    @action(detail=True, methods=["post"])  # POST /prestamos/{pk}/renovar/
    def renovar(self, request, pk=None, **kwargs):
        try:
            prestamo = services.renovar(self.get_object())
        except services.PrestamoNoRenovable as error:
            return conflicto(error)
        return Response(self.get_serializer(prestamo).data)

    @action(detail=False, methods=["get"])  # GET /prestamos/vencidos/
    def vencidos(self, request, **kwargs):
        qs = self.filter_queryset(self.get_queryset().vencidos())
        pagina = self.paginate_queryset(qs)
        if pagina is None:  # sin paginación configurada (llega en el módulo 37)
            return Response(self.get_serializer(qs, many=True).data)
        return self.get_paginated_response(self.get_serializer(pagina, many=True).data)
