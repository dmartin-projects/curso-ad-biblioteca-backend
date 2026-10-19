# usuarios/api/urls.py
from django.urls import path

from . import views

urlpatterns = [
    path("me/", views.Yo.as_view(), name="auth-me"),
]
