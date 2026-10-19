"""Ejercicio del módulo 21: plantillas de email, filtros/tags propios y PDF."""

import io
from datetime import timedelta
from decimal import Decimal

import pytest
import time_machine
from django.template import Context, Template
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader

from catalogo.models import Ejemplar, Libro
from prestamos.models import Multa, Prestamo
from prestamos.templatetags.prestamos_extras import euros
from usuarios.models import Usuario

pytestmark = pytest.mark.django_db


@pytest.fixture
def socio():
    return Usuario.objects.create_user("ana@example.com", nombre="Ana", apellidos="Gil")


@pytest.fixture
def prestamos(socio):
    libro = Libro.objects.create(titulo="Dune <edición especial>", isbn="9788497593793")
    resultado = []
    for i, dias in enumerate([2, 5]):
        ejemplar = Ejemplar.objects.create(libro=libro, codigo=f"D{i}")
        resultado.append(
            Prestamo.objects.create(
                ejemplar=ejemplar,
                socio=socio,
                fecha_limite=timezone.now() + timedelta(days=dias, hours=1),
            )
        )
    return resultado


def test_filtro_euros():
    assert euros(Decimal("1234.5")) == "1.234,50 €"
    assert euros(Decimal("2.5")) == "2,50 €"
    assert euros(None) == "—"


@pytest.mark.parametrize(("hora", "esperado"), [(9, "Buenos días"), (18, "Buenas tardes")])
def test_saludo_segun_la_hora(hora, esperado):
    madrid = timezone.get_current_timezone()
    with time_machine.travel(timezone.datetime(2026, 3, 2, hora, tzinfo=madrid), tick=False):
        assert Template("{% load prestamos_extras %}{% saludo %}").render(Context()) == esperado


def test_recordatorio_html_y_texto(socio, prestamos):
    contexto = {"socio": socio, "prestamos": prestamos, "site_url": "https://biblio.example"}
    html = render_to_string("emails/recordatorio.html", contexto)
    texto = render_to_string("emails/recordatorio.txt", contexto)

    assert "Ana" in html and "Tienes 2 préstamos que vencen pronto" in html
    assert "Dune &lt;edición especial&gt;" in html  # autoescape en el HTML
    assert 'style="' in html and "<link" not in html  # estilos en línea
    assert "Dune <edición especial>" in texto  # el texto plano no se escapa
    assert "(2 días)" in texto and "(5 días)" in texto
    assert "https://biblio.example/prestamos/" in texto


def test_inclusion_tag_resumen(socio, prestamos):
    prestamos[1].estado = Prestamo.Estado.DEVUELTO
    prestamos[1].fecha_devolucion = timezone.now()
    prestamos[1].save()
    plantilla = Template("{% load prestamos_extras %}{% resumen_prestamos socio %}")
    html = plantilla.render(Context({"socio": socio}))
    assert html.count("<li>") == 1  # solo los activos

    otro = Usuario.objects.create_user("luis@example.com")
    assert "No tienes préstamos activos" in plantilla.render(Context({"socio": otro}))


def test_partial_se_renderiza_por_separado():
    html = render_to_string("emails/factura.html#linea", {"concepto": "Multa", "importe": 2.5})
    assert html.strip() == '<tr><td>Multa</td><td style="text-align:right">2,50 €</td></tr>'


@pytest.fixture
def multa(prestamos):
    return Multa.objects.create(
        prestamo=prestamos[0], importe_base=Decimal("2.00"), recargo=Decimal("0.50")
    )


def test_recibo_pdf_solo_para_su_socio_o_bibliotecario(client, socio, multa):
    url = reverse("prestamos:recibo_multa", args=[multa.pk])
    assert client.get(url).status_code == 302  # anónimo → login

    client.force_login(Usuario.objects.create_user("luis@example.com"))
    assert client.get(url).status_code == 404  # multa ajena

    client.force_login(socio)
    r = client.get(url)
    assert r.status_code == 200
    assert r["Content-Type"] == "application/pdf"
    assert r.content.startswith(b"%PDF-")

    texto = PdfReader(io.BytesIO(r.content)).pages[0].extract_text()
    assert f"Recibo de multa nº {multa.pk}" in texto
    assert "2,50 €" in texto and "Ana Gil" in texto
    assert "Página 1 de 1" in texto
