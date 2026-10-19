# catalogo/api/urls.py
from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()  # DefaultRouter añadiría una vista raíz que no necesitamos
router.register("libros", views.LibroViewSet, basename="libro")
router.register("autores", views.AutorViewSet, basename="autor")

urlpatterns = [
    path("estadisticas/", views.estadisticas_catalogo, name="api-estadisticas"),
    path("estadisticas-cbv/", views.EstadisticasCatalogo.as_view(), name="api-estadisticas-cbv"),
    *router.urls,
]
