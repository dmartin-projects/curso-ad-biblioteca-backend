import csv
from datetime import timedelta

from django.contrib import admin, messages
from django.db.models import Count
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.urls import path
from django.utils import timezone

from catalogo.models import Libro

from . import services
from .models import Multa, Prestamo, PrestamoActivo


class RetrasoFilter(admin.SimpleListFilter):
    title = "situación"
    parameter_name = "situacion"

    def lookups(self, request, model_admin):
        return [
            ("en_plazo", "En plazo"),
            ("vencido", "Vencido"),
            ("muy_vencido", "Vencido > 30 días"),
        ]

    def queryset(self, request, queryset):
        ahora = timezone.now()
        activos = queryset.filter(estado="activo")
        match self.value():
            case "en_plazo":
                return activos.filter(fecha_limite__gte=ahora)
            case "vencido":
                return activos.filter(fecha_limite__lt=ahora)
            case "muy_vencido":
                return activos.filter(fecha_limite__lt=ahora - timedelta(days=30))
        return queryset


@admin.register(Prestamo)
class PrestamoAdmin(admin.ModelAdmin):
    list_display = ["ejemplar", "socio", "fecha_inicio", "fecha_limite", "estado"]
    list_filter = [RetrasoFilter, "estado", ("socio", admin.RelatedOnlyFieldListFilter)]
    list_select_related = ["ejemplar__libro", "socio"]
    autocomplete_fields = ["socio", "ejemplar"]
    actions = ["renovar", "marcar_devueltos", "exportar_csv"]
    change_list_template = "admin/prestamos/prestamo_change_list.html"  # añade un botón

    @admin.action(description="Renovar los préstamos seleccionados", permissions=["renovar"])
    def renovar(self, request, queryset):
        renovados, rechazados = 0, []
        for prestamo in queryset:
            try:
                services.renovar(prestamo)  # la regla del service: activo y en plazo
                renovados += 1
            except services.PrestamoNoRenovable as error:
                rechazados.append(f"{prestamo}: {error}")
        if renovados:
            self.message_user(request, f"{renovados} préstamos renovados.", messages.SUCCESS)
        for motivo in rechazados:
            self.message_user(request, motivo, messages.WARNING)

    def has_renovar_permission(self, request):
        return request.user.has_perm("prestamos.renovar_prestamo")

    @admin.action(description="Marcar como devueltos")
    def marcar_devueltos(self, request, queryset):
        for prestamo in queryset.filter(estado="activo"):
            services.devolver(
                prestamo
            )  # el servicio: ejemplar disponible, signal prestamo_devuelto…
        self.message_user(request, "Préstamos devueltos.")

    @admin.action(description="Exportar a CSV")
    def exportar_csv(self, request, queryset):
        respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
        respuesta["Content-Disposition"] = 'attachment; filename="prestamos.csv"'
        writer = csv.writer(respuesta)
        writer.writerow(["Libro", "Ejemplar", "Socio", "Inicio", "Límite", "Estado"])
        for p in queryset.select_related("ejemplar__libro", "socio"):
            writer.writerow(
                [
                    p.ejemplar.libro.titulo,
                    p.ejemplar.codigo,
                    p.socio.email,
                    p.fecha_inicio.date(),
                    p.fecha_limite.date(),
                    p.get_estado_display(),
                ]
            )
        return respuesta

    def has_delete_permission(self, request, obj=None):
        return False  # los préstamos no se borran nunca

    def get_urls(self):
        propias = [
            path(
                "estadisticas/",
                self.admin_site.admin_view(self.estadisticas_view),
                name="prestamos_prestamo_estadisticas",
            ),
        ]
        return propias + super().get_urls()  # las propias primero

    def estadisticas_view(self, request):
        contexto = {
            **self.admin_site.each_context(request),  # cabecera, menú, permisos
            "title": "Estadísticas de préstamos",
            "por_mes": Prestamo.objects.annotate(mes=TruncMonth("fecha_inicio"))
            .values("mes")
            .annotate(total=Count("id"))
            .order_by("mes"),
            "mas_prestados": Libro.objects.annotate(n=Count("ejemplares__prestamos"))
            .filter(n__gt=0)
            .order_by("-n", "titulo")[:10],
        }
        return TemplateResponse(request, "admin/prestamos/estadisticas.html", contexto)


admin.site.register(Multa)


@admin.register(PrestamoActivo)
class PrestamoActivoAdmin(admin.ModelAdmin):
    list_display = ["ejemplar", "socio", "fecha_limite"]
