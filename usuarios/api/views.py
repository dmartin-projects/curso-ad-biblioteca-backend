# usuarios/api/views.py
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from usuarios.services import (
    completar_registro,
    registro_pendiente,
    solicitar_recuperacion,
    solicitar_registro,
    usuario_desde_enlace,
)

from .auth import VistaPublicaAuth
from .serializers import (
    CambiarPasswordSerializer,
    CompletarRegistroSerializer,
    ConfirmarRecuperacionSerializer,
    RegistroSerializer,
    UsuarioSerializer,
    validar_password,
)

ENLACE_NO_VALIDO = {"detail": gettext_lazy("Enlace no válido o caducado.")}


def cerrar_todas_las_sesiones(usuario) -> None:
    """Invalida todos los refresh tokens del usuario (los access mueren solos en minutos)."""
    for token in OutstandingToken.objects.filter(user=usuario):
        BlacklistedToken.objects.get_or_create(token=token)


class Yo(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/v1/auth/me/: el usuario autenticado, sin id en la URL (no hay IDOR posible)."""

    serializer_class = UsuarioSerializer
    http_method_names = ["get", "patch", "head", "options"]  # sin PUT

    def get_object(self):
        return self.request.user


class Registro(generics.GenericAPIView):
    serializer_class = RegistroSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_scope = "registro"

    def post(self, request, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        solicitar_registro(**s.validated_data)
        # 🔐 misma respuesta para un email nuevo, pendiente o con cuenta: no revela cuáles existen
        return Response(
            {"detail": _("Revisa tu email: te hemos enviado un enlace para continuar.")},
            status=status.HTTP_202_ACCEPTED,
        )


class CompletarRegistro(VistaPublicaAuth):
    def post(self, request, **kwargs):
        s = CompletarRegistroSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        usuario = usuario_desde_enlace(s.validated_data["uid"], s.validated_data["token"])
        if usuario is None or not registro_pendiente(usuario):
            return Response(ENLACE_NO_VALIDO, status=status.HTTP_400_BAD_REQUEST)
        try:
            validar_password(s.validated_data["password"], usuario)
        except serializers.ValidationError as error:  # validadores de Django → 400
            return Response({"password": error.detail}, status=status.HTTP_400_BAD_REQUEST)
        completar_registro(usuario, s.validated_data["password"])  # contraseña + activa, a la vez
        return Response(status=status.HTTP_204_NO_CONTENT)


class CambiarPassword(generics.GenericAPIView):
    serializer_class = CambiarPasswordSerializer

    def post(self, request, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        request.user.set_password(s.validated_data["nueva"])
        request.user.save(update_fields=["password"])
        cerrar_todas_las_sesiones(request.user)  # las otras sesiones (y esta) deben volver a entrar
        return Response(status=status.HTTP_204_NO_CONTENT)


class SolicitarRecuperacion(VistaPublicaAuth):
    throttle_scope = "recuperar"

    def post(self, request, **kwargs):
        solicitar_recuperacion(request.data.get("email", ""))
        # 🔐 misma respuesta exista o no: no reveles qué emails están registrados
        return Response({"detail": _("Si el email existe, te hemos enviado un enlace.")})


class ConfirmarRecuperacion(VistaPublicaAuth):
    def post(self, request, **kwargs):
        s = ConfirmarRecuperacionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        usuario = usuario_desde_enlace(s.validated_data["uid"], s.validated_data["token"])
        if usuario is None:
            return Response(ENLACE_NO_VALIDO, status=status.HTTP_400_BAD_REQUEST)
        try:
            validar_password(s.validated_data["password"], usuario)
        except serializers.ValidationError as error:  # validadores de Django → 400
            return Response({"password": error.detail}, status=status.HTTP_400_BAD_REQUEST)
        usuario.set_password(s.validated_data["password"])
        usuario.save(update_fields=["password"])  # cambia el hash → el enlace deja de valer
        cerrar_todas_las_sesiones(usuario)
        return Response(status=status.HTTP_204_NO_CONTENT)
