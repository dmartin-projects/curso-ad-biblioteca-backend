# catalogo/fields.py
from django.db import models

from .validators import validar_isbn13


class ISBNField(models.CharField):
    description = "ISBN-13 normalizado sin guiones"

    def __init__(self, *args, **kwargs):
        kwargs["max_length"] = 13
        kwargs.setdefault("validators", [validar_isbn13])
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        # Necesario para las migraciones: qué argumentos reconstruyen el campo
        name, path, args, kwargs = super().deconstruct()
        del kwargs["max_length"]
        return name, path, args, kwargs

    def to_python(self, value):
        value = super().to_python(value)
        return value.replace("-", "").strip() if isinstance(value, str) else value

    def get_prep_value(self, value):
        # Python → base de datos
        value = super().get_prep_value(value)
        return value.replace("-", "").strip() if isinstance(value, str) else value
