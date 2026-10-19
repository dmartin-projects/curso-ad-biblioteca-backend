# usuarios/backends.py
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

Usuario = get_user_model()


class EmailONumeroSocioBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
        try:
            usuario = Usuario.objects.get(Q(email__iexact=username) | Q(socio__numero=username))
        except Usuario.DoesNotExist:
            Usuario().set_password(
                password
            )  # mismo tiempo de respuesta: evita adivinar usuarios por timing
            return None
        except Usuario.MultipleObjectsReturned:
            return None
        if usuario.check_password(password) and self.user_can_authenticate(usuario):
            return usuario
        return None
