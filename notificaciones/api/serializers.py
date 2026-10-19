# notificaciones/api/serializers.py
from rest_framework import serializers


# ── Solo para documentar (OpenAPI, módulo 38): la vista del ticket no usa GenericAPIView ──
class TicketWsSerializer(serializers.Serializer):
    ticket = serializers.CharField()
    caduca_en = serializers.IntegerField(help_text="Segundos")
