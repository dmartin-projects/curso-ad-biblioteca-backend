from django.dispatch import Signal

# Argumentos: prestamo
prestamo_devuelto = Signal()
# Argumentos: prestamo, dias_retraso
prestamo_vencido = Signal()
