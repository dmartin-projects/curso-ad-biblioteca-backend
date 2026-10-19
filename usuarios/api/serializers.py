# usuarios/api/serializers.py
from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.translation import gettext as _
from rest_framework import serializers

Usuario = get_user_model()


def validar_password(password: str, usuario) -> None:
    """Los AUTH_PASSWORD_VALIDATORS de Django, convertidos en error de DRF (400, no 500)."""
    try:
        password_validation.validate_password(password, user=usuario)
    except DjangoValidationError as error:
        raise serializers.ValidationError(list(error.messages)) from error


class UsuarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = ["id", "email", "nombre", "apellidos", "idioma", "zona_horaria", "fecha_alta"]
        read_only_fields = ["id", "email", "fecha_alta"]  # el email no se cambia con un PATCH


class RegistroSerializer(serializers.Serializer):
    """Solo datos que no son secretos: la contraseña se elige al completar el registro."""

    email = serializers.EmailField()
    nombre = serializers.CharField(max_length=150, required=False, allow_blank=True)
    apellidos = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate_email(self, email):
        # Sin comprobar si ya existe: la respuesta es la misma para un email nuevo o registrado
        return Usuario.objects.normalize_email(email).lower()


class CompletarRegistroSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})


class CambiarPasswordSerializer(serializers.Serializer):
    actual = serializers.CharField(write_only=True)
    nueva = serializers.CharField(write_only=True)

    def validate_actual(self, valor):
        if not self.context["request"].user.check_password(valor):
            raise serializers.ValidationError(_("La contraseña actual no es correcta."))
        return valor

    def validate_nueva(self, valor):
        validar_password(valor, self.context["request"].user)
        return valor


class ConfirmarRecuperacionSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True)
