# catalogo/api/urls.py
from django.urls import path

from . import views

urlpatterns = [
    path("estadisticas/", views.estadisticas_catalogo, name="api-estadisticas"),
    path("estadisticas-cbv/", views.EstadisticasCatalogo.as_view(), name="api-estadisticas-cbv"),
]
