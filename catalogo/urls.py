# catalogo/urls.py
from django.urls import path, register_converter

from . import archivos, asincrono, converters, views

register_converter(converters.ISBNConverter, "isbn")
register_converter(converters.AnioConverter, "anio")

app_name = "catalogo"

urlpatterns = [
    path("libros/", views.lista_libros, name="lista_libros"),
    path("libros/nuevo/", views.crear_libro, name="crear_libro"),
    path("libros/buscar/", views.buscar_libros, name="buscar_libros"),
    path("recientes/", views.recientes, name="recientes"),
    path("autores/autocompletar/", views.autocompletar_autores, name="autocompletar_autores"),
    path("libros/isbn/<isbn:isbn>/", views.libro_por_isbn, name="libro_por_isbn"),
    path("libros/anio/<anio:anio>/", views.libros_por_anio, name="libros_por_anio"),
    path("libros/<int:pk>/", views.detalle_libro, name="detalle_libro"),
    # módulo 24: asíncrono
    path("libros/isbn/<isbn:isbn>/info/", asincrono.info_libro, name="info_libro"),
    path(
        "libros/isbn/<isbn:isbn>/info-secuencial/",
        asincrono.info_libro_secuencial,
        name="info_libro_secuencial",
    ),
    # módulo 20: archivos
    path("libros/<int:pk>/portada/", archivos.subir_portada, name="subir_portada"),
    path("libros/<int:pk>/ficha/", archivos.subir_ficha, name="subir_ficha"),
    path("libros/<int:pk>/ficha/descargar/", archivos.descargar_ficha, name="descargar_ficha"),
    path("prestamos/exportar/", archivos.exportar_prestamos, name="exportar_prestamos"),
    path("autores/<slug:slug>/", views.detalle_autor, name="detalle_autor"),
    # módulo 04: las versiones CBV
    path("v2/libros/", views.LibroListJSON.as_view(), name="lista_libros_cbv"),
    path("v2/libros/exportar/", views.ExportarLibrosCSV.as_view(), name="exportar_libros"),
    path("v2/autores/<slug:slug>/", views.AutorDetailJSON.as_view(), name="detalle_autor_cbv"),
]
