from django import forms
from django.forms import BaseFormSet, formset_factory

from .models import Libro
from .validators import validar_isbn13


class BusquedaAvanzadaForm(forms.Form):
    q = forms.CharField(required=False, max_length=100, strip=True)
    desde = forms.IntegerField(required=False, min_value=1450, max_value=2100)
    hasta = forms.IntegerField(required=False, min_value=1450, max_value=2100)
    solo_disponibles = forms.BooleanField(required=False)

    def clean_q(self):
        q = self.cleaned_data["q"]
        if q and len(q) < 2:
            raise forms.ValidationError("Escribe al menos 2 caracteres.", code="corto")
        return q.lower()

    def clean(self):
        datos = super().clean()
        desde, hasta = datos.get("desde"), datos.get("hasta")
        if desde and hasta and desde > hasta:
            self.add_error("hasta", "Debe ser mayor o igual que 'desde'.")
        return datos


class LibroForm(forms.ModelForm):
    class Meta:
        model = Libro
        fields = ["titulo", "isbn", "autores", "publicado"]
        labels = {"isbn": "ISBN-13"}
        help_texts = {"isbn": "Sin guiones."}
        error_messages = {"isbn": {"unique": "Ya existe un libro con ese ISBN."}}

    def clean_titulo(self):
        return self.cleaned_data["titulo"].strip()


class FilaImportacionForm(forms.Form):
    isbn = forms.CharField(validators=[validar_isbn13])
    titulo = forms.CharField(max_length=300)
    autor = forms.CharField(max_length=200)


class BaseFilasFormSet(BaseFormSet):
    def clean(self):
        if any(self.errors):
            return
        vistos = set()
        for form in self.forms:
            isbn = form.cleaned_data.get("isbn")
            if isbn in vistos:
                raise forms.ValidationError(
                    f"ISBN repetido en el archivo: {isbn}", code="duplicado"
                )
            vistos.add(isbn)


FilasFormSet = formset_factory(FilaImportacionForm, formset=BaseFilasFormSet, extra=0)


def a_datos_formset(filas: list[dict]) -> dict:
    datos = {"form-TOTAL_FORMS": str(len(filas)), "form-INITIAL_FORMS": "0"}
    for i, fila in enumerate(filas):
        for clave, valor in fila.items():
            datos[f"form-{i}-{clave}"] = valor
    return datos
