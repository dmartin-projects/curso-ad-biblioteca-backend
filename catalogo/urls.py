# catalogo/urls.py
from django.urls import path, register_converter

from . import converters, views

register_converter(converters.ISBNConverter, "isbn")
register_converter(converters.AnioConverter, "anio")

app_name = "catalogo"

urlpatterns = [
    path("libros/", views.lista_libros, name="lista_libros"),
    path("libros/nuevo/", views.crear_libro, name="crear_libro"),
    path("libros/isbn/<isbn:isbn>/", views.libro_por_isbn, name="libro_por_isbn"),
    path("libros/anio/<anio:anio>/", views.libros_por_anio, name="libros_por_anio"),
    path("libros/<int:pk>/", views.detalle_libro, name="detalle_libro"),
    path("autores/<slug:slug>/", views.detalle_autor, name="detalle_autor"),
    # módulo 04: las versiones CBV
    path("v2/libros/", views.LibroListJSON.as_view(), name="lista_libros_cbv"),
    path("v2/libros/exportar/", views.ExportarLibrosCSV.as_view(), name="exportar_libros"),
    path("v2/autores/<slug:slug>/", views.AutorDetailJSON.as_view(), name="detalle_autor_cbv"),
]
