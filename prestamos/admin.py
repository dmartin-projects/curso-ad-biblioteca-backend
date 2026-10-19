from django.contrib import admin

from .models import Multa, Prestamo, PrestamoActivo

admin.site.register([Prestamo, Multa])


@admin.register(PrestamoActivo)
class PrestamoActivoAdmin(admin.ModelAdmin):
    list_display = ["ejemplar", "socio", "fecha_limite"]
