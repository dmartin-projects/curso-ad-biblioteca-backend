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
