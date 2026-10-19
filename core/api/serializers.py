# core/api/serializers.py — solo para DOCUMENTAR formas comunes en OpenAPI (módulo 38)
from rest_framework import serializers


class ProblemaSerializer(serializers.Serializer):
    """El formato único de error de la API (core.api.exceptions)."""

    type = serializers.CharField()
    title = serializers.CharField()
    status = serializers.IntegerField()
    detail = serializers.JSONField(allow_null=True)
    errors = serializers.DictField(
        child=serializers.ListField(child=serializers.CharField()), allow_null=True
    )
    request_id = serializers.CharField()


class MensajeSerializer(serializers.Serializer):
    detail = serializers.CharField()
