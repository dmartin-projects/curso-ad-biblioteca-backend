# prestamos/api/serializers.py
from rest_framework import serializers

from catalogo.models import Libro
from prestamos.models import Prestamo


class PrestarSerializer(serializers.Serializer):
    """ENTRADA: lo único que el cliente puede decidir. El socio es quien llama."""

    ejemplar_id = serializers.IntegerField(min_value=1)


class LibroMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Libro
        fields = ["id", "titulo", "isbn"]


class PrestamoSerializer(serializers.ModelSerializer):
    """SALIDA: el préstamo con su libro anidado."""

    libro = LibroMiniSerializer(source="ejemplar.libro", read_only=True)
    ejemplar = serializers.CharField(source="ejemplar.codigo", read_only=True)

    class Meta:
        model = Prestamo
        fields = ["id", "libro", "ejemplar", "estado", "fecha_inicio", "fecha_limite"]
        read_only_fields = fields
