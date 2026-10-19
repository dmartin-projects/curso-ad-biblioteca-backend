# usuarios/api/auth.py
from django.conf import settings
from django.db import transaction
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.exceptions import NotAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from core.api.serializers import ProblemaSerializer

from .serializers import AccessSerializer, LoginSerializer


def _poner_cookie_refresh(response, refresh: str):
    cfg = settings.JWT_REFRESH_COOKIE
    response.set_cookie(
        cfg["key"],
        refresh,
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        path=cfg["path"],
        httponly=cfg["httponly"],
        secure=cfg["secure"],
        samesite=cfg["samesite"],
    )


def _bloquear(refresh: str) -> None:
    """SELECT … FOR UPDATE del token en la tabla de emitidos; el serializer lo valida después."""
    # verify=False: solo leer el jti (firma, caducidad y blacklist las comprueba el serializer).
    # Con .get(): una cookie forjada puede no traer jti, y entonces no hay fila que bloquear (→ 401)
    jti = RefreshToken(refresh, verify=False).get(api_settings.JTI_CLAIM)
    if jti:
        list(OutstandingToken.objects.select_for_update().filter(jti=jti))


class VistaPublicaAuth(APIView):
    """Base para login/refresh/registro: no autentica la petición, pero responde 401 (no 403)."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []  # un access caducado en la cabecera no debe estorbar

    def get_authenticate_header(self, request):
        return 'Bearer realm="api"'


class Login(VistaPublicaAuth):
    throttle_scope = "login"  # 5/min (DEFAULT_THROTTLE_RATES)

    @extend_schema(
        request=LoginSerializer, responses={200: AccessSerializer, 401: ProblemaSerializer}
    )
    def post(self, request, **kwargs):
        # campos: email (USERNAME_FIELD) y password. Con la request en el context, authenticate()
        # la recibe: los backends y la signal user_login_failed saben de dónde viene el intento
        serializer = TokenObtainPairSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)  # credenciales malas → 401
        tokens = serializer.validated_data
        response = Response({"access": tokens["access"]})
        _poner_cookie_refresh(response, tokens["refresh"])
        return response


class Refresh(VistaPublicaAuth):
    @extend_schema(request=None, responses={200: AccessSerializer, 401: ProblemaSerializer})
    def post(self, request, **kwargs):
        refresh = request.COOKIES.get(settings.JWT_REFRESH_COOKIE["key"])
        if not refresh:
            raise NotAuthenticated(_("Sin sesión."))  # el exception handler le da el formato común
        serializer = TokenRefreshSerializer(data={"refresh": refresh})
        try:
            # Rotación atómica: dos requests con la misma cookie (dos pestañas, un robo) se ponen en
            # fila con el bloqueo; la segunda ya la ve en la lista negra → 401. Sin él, las dos rotan
            with transaction.atomic():
                _bloquear(refresh)
                serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            raise InvalidToken(exc.args[0]) from exc
        response = Response({"access": serializer.validated_data["access"]})
        _poner_cookie_refresh(response, serializer.validated_data["refresh"])  # rotación
        return response


class Logout(VistaPublicaAuth):
    @extend_schema(request=None, responses={204: None})
    def post(self, request, **kwargs):
        cfg = settings.JWT_REFRESH_COOKIE
        if refresh := request.COOKIES.get(cfg["key"]):
            try:
                RefreshToken(refresh).blacklist()
            except TokenError:
                pass  # ya caducado o inválido: da igual
        response = Response(status=status.HTTP_204_NO_CONTENT)
        response.delete_cookie(cfg["key"], path=cfg["path"], samesite=cfg["samesite"])
        return response
