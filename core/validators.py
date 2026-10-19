# core/validators.py
from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext as _


@deconstructible
class TamanoMaximoValidator:
    def __init__(self, megas: int):
        self.megas = megas

    def __call__(self, archivo):
        if archivo.size > self.megas * 1024 * 1024:
            raise ValidationError(
                _("El archivo supera %(megas)s MB."),
                code="demasiado_grande",
                params={"megas": self.megas},
            )

    def __eq__(self, other):
        return isinstance(other, TamanoMaximoValidator) and self.megas == other.megas


def validar_pdf_real(archivo):
    cabecera = archivo.read(5)
    archivo.seek(0)  # ⚠️ vuelve al principio
    if cabecera != b"%PDF-":
        raise ValidationError(_("El archivo no es un PDF válido."), code="no_pdf")


@deconstructible
class TipoRealValidator:
    """Comprueba el tipo por el CONTENIDO (libmagic), no por la extensión ni el Content-Type."""

    def __init__(self, tipos: list[str]):
        self.tipos = list(tipos)

    def __call__(self, archivo):
        import magic  # uv add python-magic (macOS: brew install libmagic)

        cabecera = archivo.read(2048)
        archivo.seek(0)
        tipo = magic.from_buffer(cabecera, mime=True)
        if tipo not in self.tipos:
            raise ValidationError(
                _("Tipo de archivo no admitido (%(tipo)s)."),
                code="tipo_no_admitido",
                params={"tipo": tipo},
            )

    def __eq__(self, other):
        return isinstance(other, TipoRealValidator) and self.tipos == other.tipos
