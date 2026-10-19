# catalogo/validators.py
from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext as _


def validar_isbn13(valor: str) -> None:
    digitos = valor.replace("-", "")
    if len(digitos) != 13 or not digitos.isdigit():
        raise ValidationError(_("El ISBN debe tener 13 dígitos."), code="isbn_formato")
    suma = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(digitos[:12]))
    control = (10 - suma % 10) % 10
    if control != int(digitos[12]):
        raise ValidationError(_("El dígito de control del ISBN no es válido."), code="isbn_control")


@deconstructible  # necesario si se usa en un modelo con argumentos (para las migraciones)
class PalabrasProhibidasValidator:
    def __init__(self, palabras: list[str]):
        self.palabras = [p.lower() for p in palabras]

    def __call__(self, valor: str) -> None:
        encontradas = [p for p in self.palabras if p in valor.lower()]
        if encontradas:
            raise ValidationError(
                "Contiene palabras no permitidas: %(lista)s",
                code="palabras_prohibidas",
                params={"lista": ", ".join(encontradas)},
            )

    def __eq__(self, other):
        return isinstance(other, PalabrasProhibidasValidator) and self.palabras == other.palabras
