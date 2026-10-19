from django.contrib import admin
from django.db.models import Count, Exists, OuterRef

from .models import Autor, Ejemplar, Genero, Libro


class AutoriaInline(admin.TabularInline):  # en filas
    model = Libro.autores.through
    extra = 0
    min_num = 1  # al menos un autor
    autocomplete_fields = ["autor"]


class EjemplarInline(admin.StackedInline):  # en bloques
    model = Ejemplar
    extra = 0
    fields = ["codigo", "estado"]
    show_change_link = True  # enlace a su página completa


@admin.register(Libro)
class LibroAdmin(admin.ModelAdmin):
    list_display = ["titulo", "isbn", "lista_autores", "publicado", "n_ejemplares", "disponible"]
    list_display_links = ["titulo"]
    list_filter = ["generos", ("publicado", admin.DateFieldListFilter)]
    search_fields = ["titulo", "isbn", "autores__nombre"]
    search_help_text = "Busca por título, ISBN o autor"
    date_hierarchy = "publicado"
    ordering = ["titulo"]
    list_per_page = 50
    show_full_result_count = False  # evita un COUNT(*) caro en tablas enormes
    inlines = [AutoriaInline, EjemplarInline]
    fieldsets = [
        (None, {"fields": ["titulo", "isbn", "sinopsis"]}),
        ("Clasificación", {"fields": ["generos", "publicado", "paginas", "etiquetas"]}),
        ("Metadatos", {"fields": ["metadatos", "creado", "actualizado"], "classes": ["collapse"]}),
    ]
    readonly_fields = ["creado", "actualizado"]
    filter_horizontal = ["generos"]
    save_on_top = True

    def get_queryset(self, request):
        # Un número fijo de consultas para todo el listado: sin N+1
        disponible = Ejemplar.objects.filter(
            libro=OuterRef("pk"), estado=Ejemplar.Estado.DISPONIBLE
        )
        return (
            super()
            .get_queryset(request)
            .prefetch_related("autores")
            .annotate(
                _n_ejemplares=Count("ejemplares", distinct=True),
                _disponible=Exists(disponible),
            )
        )

    @admin.display(description="Autores")
    def lista_autores(self, obj):
        return ", ".join(a.nombre for a in obj.autores.all())  # usa el prefetch

    @admin.display(description="Ejemplares", ordering="_n_ejemplares")
    def n_ejemplares(self, obj):
        return obj._n_ejemplares

    @admin.display(description="Disponible", boolean=True, ordering="_disponible")
    def disponible(self, obj):
        return obj._disponible

    def get_readonly_fields(self, request, obj=None):
        if obj and not request.user.is_superuser:
            return [*self.readonly_fields, "isbn"]  # el ISBN no se toca tras crear
        return self.readonly_fields


@admin.register(Autor)
class AutorAdmin(admin.ModelAdmin):
    list_display = ["nombre", "apellidos", "slug"]
    search_fields = ["nombre", "apellidos"]  # obligatorio para usarlo en autocomplete
    prepopulated_fields = {"slug": ["nombre"]}


@admin.register(Ejemplar)
class EjemplarAdmin(admin.ModelAdmin):
    list_display = ["codigo", "libro", "estado"]
    list_filter = ["estado"]
    search_fields = ["codigo", "libro__titulo"]
    autocomplete_fields = ["libro"]


@admin.register(Genero)
class GeneroAdmin(admin.ModelAdmin):
    list_display = ["nombre", "padre"]
    search_fields = ["nombre"]
