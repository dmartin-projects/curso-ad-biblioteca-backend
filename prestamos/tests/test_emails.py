"""Ejercicio del módulo 22: emails con texto + HTML, adjunto y SMTP real (simulado)."""

import socket
from datetime import timedelta
from decimal import Decimal
from email import message_from_bytes, policy

import pytest
from aiosmtpd.controller import Controller
from django.core import mail
from django.utils import timezone

from catalogo.models import Ejemplar, Libro
from prestamos.emails import enviar_recibo_multa, enviar_recordatorio
from prestamos.models import Multa, Prestamo
from usuarios.models import Usuario

pytestmark = pytest.mark.django_db


@pytest.fixture
def socio_con_prestamos():
    socio = Usuario.objects.create_user("ana@example.com", nombre="Ana", apellidos="Gil")
    libro = Libro.objects.create(titulo="Dune", isbn="9788497593793")
    ejemplar = Ejemplar.objects.create(libro=libro, codigo="D1")
    Prestamo.objects.create(
        ejemplar=ejemplar, socio=socio, fecha_limite=timezone.now() + timedelta(days=2)
    )
    return socio


def test_recordatorio(socio_con_prestamos):
    socio = socio_con_prestamos
    enviar_recordatorio(socio, socio.prestamos.all())

    assert len(mail.outbox) == 1
    m = mail.outbox[0]
    assert [str(d) for d in m.to] == ["Ana Gil <ana@example.com>"]  # m.to guarda los Address
    assert m.from_email == '"Biblioteca" <no-responder@biblioteca.example>'
    assert "vencen pronto" in m.subject
    assert "Dune" in m.body  # texto plano
    html, tipo = m.alternatives[0]
    assert tipo == "text/html" and "<table" in html
    assert m.extra_headers["List-Unsubscribe"] == "<mailto:baja@biblioteca.example>"
    assert m.sent_using == "default"  # Django 6.1


def test_recibo_adjunto(socio_con_prestamos):
    prestamo = socio_con_prestamos.prestamos.get()
    multa = Multa.objects.create(prestamo=prestamo, importe_base=Decimal("2.50"))
    enviar_recibo_multa(multa)

    (m,) = mail.outbox
    nombre, contenido, tipo = m.attachments[0]
    assert nombre == f"recibo-{multa.pk}.pdf"
    assert tipo == "application/pdf" and contenido.startswith(b"%PDF-")


def test_no_se_pueden_inyectar_cabeceras(socio_con_prestamos):
    socio = socio_con_prestamos
    socio.nombre = "Ana\nBcc: espia@example.com"
    with pytest.raises(ValueError):
        enviar_recordatorio(socio, socio.prestamos.all())
    assert mail.outbox == []


class Buzon:
    """Servidor SMTP de pega: guarda lo que recibe (como Mailpit, sin Docker)."""

    def __init__(self):
        self.mensajes = []

    async def handle_DATA(self, server, session, envelope):  # noqa: N802 (API de aiosmtpd)
        self.mensajes.append(
            message_from_bytes(envelope.content, policy=policy.default)
        )  # decodifica cabeceras
        return "250 OK"


def puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_envio_por_smtp(settings, socio_con_prestamos):
    buzon = Buzon()
    servidor = Controller(buzon, hostname="127.0.0.1", port=puerto_libre())
    servidor.start()
    try:
        settings.MAILERS = {  # lo mismo que dev.py con USAR_MAILPIT=1
            "default": {
                "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
                "OPTIONS": {"host": "127.0.0.1", "port": servidor.port, "timeout": 5},
            }
        }
        enviar_recordatorio(socio_con_prestamos, socio_con_prestamos.prestamos.all())
    finally:
        servidor.stop()

    (recibido,) = buzon.mensajes
    assert recibido["Subject"] == "Tus préstamos vencen pronto"
    assert recibido.get_content_type() == "multipart/alternative"
    tipos = [parte.get_content_type() for parte in recibido.iter_parts()]
    assert tipos == ["text/plain", "text/html"]
