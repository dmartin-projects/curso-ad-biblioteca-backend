import csv
from dataclasses import dataclass, field
from pathlib import Path

from django import forms
from django.db import transaction
from django.utils.text import slugify

from .forms import BaseFilasFormSet, FilaImportacionForm, a_datos_formset
from .models import Autor, Libro


class FilaCSVForm(FilaImportacionForm):
    publicado = forms.DateField(required=False)


FilasCSVFormSet = forms.formset_factory(FilaCSVForm, formset=BaseFilasFormSet, extra=0)


@dataclass
class ResultadoImportacion:
    creados: int = 0
    existentes: int = 0
    errores: list[str] = field(default_factory=list)


def leer_csv(ruta: Path, delimitador: str = ";") -> list[dict]:
    with ruta.open(encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=delimitador))


def importar_libros(filas: list[dict], guardar: bool = True) -> ResultadoImportacion:
    """Valida TODAS las filas con el formset (módulo 05); solo si todas son válidas, guarda."""
    resultado = ResultadoImportacion()
    formset = FilasCSVFormSet(data=a_datos_formset(filas))
    if not formset.is_valid():
        for n, errores in enumerate(formset.errors, start=1):
            for campo, mensajes in errores.items():
                resultado.errores.append(f"Fila {n}, {campo}: {' '.join(mensajes)}")
        resultado.errores += [str(e) for e in formset.non_form_errors()]
        return resultado

    with transaction.atomic():
        for datos in (form.cleaned_data for form in formset):
            autor, _ = Autor.objects.get_or_create(
                slug=slugify(datos["autor"]), defaults={"nombre": datos["autor"]}
            )
            libro, nuevo = Libro.objects.get_or_create(
                isbn=datos["isbn"].replace("-", ""),
                defaults={"titulo": datos["titulo"], "publicado": datos["publicado"]},
            )
            libro.autores.add(autor)
            if nuevo:
                resultado.creados += 1
            else:
                resultado.existentes += 1
        if not guardar:
            transaction.set_rollback(True)  # dry-run: se ha ejecutado todo y se deshace al final
    return resultado
