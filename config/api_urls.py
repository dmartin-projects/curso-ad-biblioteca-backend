# config/api_urls.py — todas las API bajo /api/<version>/
from django.urls import include, path

urlpatterns = [
    path("", include("catalogo.api.urls")),
    path("", include("prestamos.api.urls")),
    path("auth/", include("usuarios.api.urls")),
]
