# tickets/models.py — versión simplificada del proyecto final (módulo 26)
from django.db import models


class Ticket(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        PROCESANDO = "procesando", "Procesando"
        PROCESADO = "procesado", "Procesado"
        ERROR = "error", "Error"

    texto = models.TextField(help_text="Lo que 'leería' el OCR")
    estado = models.CharField(max_length=12, choices=Estado, default=Estado.PENDIENTE)
    intentos = models.PositiveSmallIntegerField(default=0)
    creado = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Ticket {self.pk} ({self.estado})"


class Gasto(models.Model):
    ticket = models.OneToOneField(Ticket, on_delete=models.CASCADE, related_name="gasto")
    comercio = models.CharField(max_length=100)
    importe = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.comercio}: {self.importe} €"
