# prestamos/api/urls.py
from django.urls import path

from . import views

urlpatterns = [
    path("prestamos/<int:pk>/devolver/", views.DevolverPrestamo.as_view(), name="api-devolver"),
]
