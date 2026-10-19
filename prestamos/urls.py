from django.urls import path

from . import views

app_name = "prestamos"

urlpatterns = [
    path("renovar/<str:token>/", views.renovar, name="renovar"),
    path("", views.MisPrestamos.as_view(), name="lista"),
    path("<int:pk>/", views.DetallePrestamo.as_view(), name="detalle"),
    path("<int:pk>/renovar/", views.RenovarPrestamo.as_view(), name="renovar_pk"),
    path("multas/<int:pk>/recibo/", views.descargar_recibo, name="recibo_multa"),
]
