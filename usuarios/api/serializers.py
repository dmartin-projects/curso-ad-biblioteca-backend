# usuarios/api/serializers.py
from rest_framework import serializers

from usuarios.models import Usuario


class UsuarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = ["id", "email", "nombre", "apellidos", "idioma", "zona_horaria"]
        read_only_fields = [
            "id",
            "email",
        ]  # el email no se cambia con un PATCH (exigiría verificarlo)
