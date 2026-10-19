# notificaciones/api/views.py
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from notificaciones.middleware import DURACION_TICKET, crear_ticket


class TicketWebSocketView(APIView):
    """Ticket de un solo uso para abrir el WebSocket: el JWT nunca viaja en la URL."""

    def post(self, request, *args, **kwargs):
        return Response(
            {"ticket": crear_ticket(request.user), "caduca_en": DURACION_TICKET},
            status=status.HTTP_201_CREATED,
        )
