# catalogo/api/fields.py
from rest_framework import serializers


class ISBNSerializerField(serializers.CharField):
    def to_internal_value(self, data):
        valor = super().to_internal_value(data)
        return valor.replace("-", "").replace(" ", "")
