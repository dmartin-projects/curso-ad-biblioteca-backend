# prestamos/api/views.py
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from catalogo.models import Ejemplar
from prestamos.models import Prestamo
from prestamos.services import (
    EjemplarNoDisponible,
    LimitePrestamosAlcanzado,
    PrestamoYaDevuelto,
    devolver,
    prestar,
)

from .serializers import PrestamoSerializer, PrestarSerializer


def prestamos_visibles(user):
    """El socio, los suyos; el bibliotecario, todos (la regla del módulo 14)."""
    qs = Prestamo.objects.all()
    return qs if user.has_perm("prestamos.view_prestamo") else qs.filter(socio=user)


class DevolverPrestamo(APIView):
    def post(self, request, version, pk):
        prestamo = get_object_or_404(prestamos_visibles(request.user), pk=pk)  # ajeno → 404
        try:
            prestamo = devolver(prestamo)
        except PrestamoYaDevuelto:
            return Response(
                {"detail": _("El préstamo ya estaba devuelto.")}, status=status.HTTP_409_CONFLICT
            )
        multa = getattr(prestamo, "multa", None)
        return Response(
            {
                "id": prestamo.pk,
                "estado": prestamo.estado,
                "multa": str(multa.importe_base) if multa else None,  # decimales como cadena
            }
        )


class CrearPrestamo(APIView):
    """POST /api/v1/prestamos/ — el socio autenticado se lleva un ejemplar (módulo 33)."""

    def post(self, request, version):
        entrada = PrestarSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)  # 400 con los errores por campo
        try:
            prestamo = prestar(entrada.validated_data["ejemplar_id"], socio=request.user)
        except Ejemplar.DoesNotExist:
            return Response(
                {"ejemplar_id": [_("No existe ese ejemplar.")]}, status=status.HTTP_400_BAD_REQUEST
            )
        except EjemplarNoDisponible as error:
            return Response({"detail": str(error)}, status=status.HTTP_409_CONFLICT)
        except LimitePrestamosAlcanzado as error:  # el máximo del perfil (módulo 15)
            return Response({"detail": str(error)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        prestamo = Prestamo.objects.get(pk=prestamo.pk)  # recarga: fecha_inicio la pone la BD
        return Response(PrestamoSerializer(prestamo).data, status=status.HTTP_201_CREATED)
