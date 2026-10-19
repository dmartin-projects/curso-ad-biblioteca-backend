# config/urls.py
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from . import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", views.health, name="health"),
    path("catalogo/", include("catalogo.urls")),
    path("libros/", RedirectView.as_view(pattern_name="catalogo:lista_libros")),
]
