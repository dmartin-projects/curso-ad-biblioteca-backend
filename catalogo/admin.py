from django.contrib import admin

from .models import Autor, Autoria, Ejemplar, Genero, Libro

admin.site.register([Autor, Genero, Autoria, Ejemplar])


class AutoriaInline(admin.TabularInline):
    model = Autoria
    extra = 1


@admin.register(Libro)
class LibroAdmin(admin.ModelAdmin):
    inlines = [AutoriaInline]
