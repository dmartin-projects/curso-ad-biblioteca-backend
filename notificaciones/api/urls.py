# notificaciones/api/urls.py
from django.urls import path

from .views import TicketWebSocketView

urlpatterns = [
    path("notificaciones/ws-ticket/", TicketWebSocketView.as_view(), name="ws-ticket"),
]
