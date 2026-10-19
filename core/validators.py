# core/validators.py
from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible


@deconstructible
class TamanoMaximoValidator:
    def __init__(self, megas: int):
        self.megas = megas

    def __call__(self, archivo):
        if archivo.size > self.megas * 1024 * 1024:
            raise ValidationError(f"El archivo supera {self.megas} MB.", code="demasiado_grande")

    def __eq__(self, other):
        return isinstance(other, TamanoMaximoValidator) and self.megas == other.megas


def validar_pdf_real(archivo):
    cabecera = archivo.read(5)
    archivo.seek(0)  # ⚠️ vuelve al principio
    if cabecera != b"%PDF-":
        raise ValidationError("El archivo no es un PDF válido.", code="no_pdf")
