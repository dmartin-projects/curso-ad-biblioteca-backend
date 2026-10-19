# config/urls.py
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from core import views as core_views

from . import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", views.health, name="health"),
    path("catalogo/", include("catalogo.urls")),
    path("prestamos/", include("prestamos.urls")),
    path("notas/<str:app>/<str:modelo>/<int:pk>/", core_views.notas, name="notas"),
    path("cuentas/", include("django.contrib.auth.urls")),
    path("libros/", RedirectView.as_view(pattern_name="catalogo:lista_libros")),
]
