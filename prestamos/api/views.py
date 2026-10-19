# prestamos/api/views.py
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from prestamos.models import Prestamo
from prestamos.services import PrestamoYaDevuelto, devolver


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
