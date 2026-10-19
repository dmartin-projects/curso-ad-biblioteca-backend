# usuarios/api/views.py
from rest_framework import generics

from .serializers import UsuarioSerializer


class Yo(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/v1/auth/me/: el usuario autenticado, sin id en la URL (no hay IDOR posible)."""

    serializer_class = UsuarioSerializer
    http_method_names = ["get", "patch", "head", "options"]  # sin PUT

    def get_object(self):
        return self.request.user
