from django.urls import path

from . import views

app_name = "prestamos"

urlpatterns = [
    path("renovar/<str:token>/", views.renovar, name="renovar"),
]
