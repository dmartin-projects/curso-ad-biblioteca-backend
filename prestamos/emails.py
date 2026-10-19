# prestamos/emails.py — composición de emails (módulo 22)
from email.headerregistry import Address

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import translation
from django.utils.translation import gettext as _

from .pdf import recibo_multa_pdf


def destinatario(usuario) -> Address:
    """Nunca f"{nombre} <{email}>": un nombre con saltos de línea inyectaría cabeceras."""
    return Address(display_name=usuario.get_full_name(), addr_spec=usuario.email)


def crear_recordatorio(socio, prestamos) -> EmailMultiAlternatives:
    contexto = {"socio": socio, "prestamos": prestamos, "site_url": settings.SITE_URL}
    # En una tarea no hay petición ni idioma activo: el del destinatario (módulo 28)
    with translation.override(getattr(socio, "idioma", None) or settings.LANGUAGE_CODE):
        mensaje = EmailMultiAlternatives(
            subject=_("Tus préstamos vencen pronto"),
            body=render_to_string("emails/recordatorio.txt", contexto),
            to=[destinatario(socio)],
            reply_to=["biblioteca@biblioteca.example"],
            headers={"List-Unsubscribe": "<mailto:baja@biblioteca.example>"},
        )
        html = render_to_string("emails/recordatorio.html", contexto)
    mensaje.attach_alternative(html, "text/html")
    return mensaje


def enviar_recordatorio(socio, prestamos) -> None:
    crear_recordatorio(socio, prestamos).send()


def enviar_recibo_multa(multa) -> None:
    socio = multa.prestamo.socio
    mensaje = EmailMultiAlternatives(
        subject=f"Recibo de la multa nº {multa.pk}",
        body=(
            f"Hola {socio.get_short_name()}:\n\n"
            "Te adjuntamos el recibo de tu multa en PDF.\n\nBiblioteca"
        ),
        to=[destinatario(socio)],
    )
    mensaje.attach(f"recibo-{multa.pk}.pdf", recibo_multa_pdf(multa), "application/pdf")
    mensaje.send()


def enviar_confirmacion(prestamo) -> None:
    """Módulo 26: lo envía una tarea de django.tasks, nunca la petición."""
    EmailMultiAlternatives(
        subject=f"Préstamo confirmado: {prestamo.ejemplar.libro.titulo}",
        body=(
            f"Hola {prestamo.socio.get_short_name()}:\n\n"
            f"Te has llevado «{prestamo.ejemplar.libro.titulo}». "
            f"Devuélvelo antes del {prestamo.fecha_limite:%d/%m/%Y}.\n\nBiblioteca"
        ),
        to=[destinatario(prestamo.socio)],
    ).send()
