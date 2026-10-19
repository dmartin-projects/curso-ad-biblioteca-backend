# core/models.py   (crea la app: uv run python manage.py startapp core y añádela a LOCAL_APPS)
from django.db import models

class ModeloConFechas(models.Model):
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
