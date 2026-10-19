# catalogo/archivos.py — vistas de subida y descarga (módulo 20)
import csv

from django import forms
from django.contrib.admin.views.decorators import staff_member_required
from django.http import FileResponse, Http404, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_GET, require_POST
from storages.backends.s3 import S3Storage

from prestamos.models import Prestamo

from .models import Libro


class PortadaForm(forms.ModelForm):
    class Meta:
        model = Libro
        fields = ["portada"]


class FichaForm(forms.ModelForm):
    class Meta:
        model = Libro
        fields = ["ficha_pdf"]


def _subir(request, pk, form_class, campo):
    libro = get_object_or_404(Libro, pk=pk)
    form = form_class(data=request.POST, files=request.FILES, instance=libro)  # ⚠️ files=
    if not form.is_valid():
        return JsonResponse({"errores": form.errors.get_json_data()}, status=400)
    form.save()
    return JsonResponse({campo: getattr(libro, campo).url})


@staff_member_required  # sin sesión de staff → redirige al login del admin
@require_POST
def subir_portada(request, pk):
    return _subir(request, pk, PortadaForm, "portada")


@staff_member_required
@require_POST
def subir_ficha(request, pk):
    return _subir(request, pk, FichaForm, "ficha_pdf")


@staff_member_required
@require_GET
def descargar_ficha(request, pk):
    libro = get_object_or_404(Libro, pk=pk)
    if not libro.ficha_pdf:
        raise Http404("Este libro no tiene ficha.")
    if isinstance(libro.ficha_pdf.storage, S3Storage):
        return redirect(libro.ficha_pdf.url)  # opción A: URL firmada, Django no transfiere bytes
    return FileResponse(  # opción B: almacenamiento local (desarrollo, tests)
        libro.ficha_pdf.open("rb"), as_attachment=True, filename=f"{libro.isbn}.pdf"
    )


class Eco:
    """Objeto 'archivo' cuyo write devuelve lo escrito (para csv.writer)."""

    def write(self, valor):
        return valor


CABECERA = ["id", "libro", "socio", "inicio", "estado"]


def filas_prestamos():
    """Generador: nunca hay más de chunk_size préstamos en memoria."""
    writer = csv.writer(Eco())
    yield writer.writerow(CABECERA)
    prestamos = (
        Prestamo.objects.select_related("ejemplar__libro", "socio")
        .order_by("pk")
        .iterator(chunk_size=2000)
    )
    for p in prestamos:
        yield writer.writerow(
            [p.pk, p.ejemplar.libro.titulo, p.socio.email, p.fecha_inicio.isoformat(), p.estado]
        )


@staff_member_required
@require_GET
def exportar_prestamos(request):
    return StreamingHttpResponse(
        filas_prestamos(),
        content_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="prestamos.csv"'},
    )
