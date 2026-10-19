# prestamos/pdf.py
from django.conf import settings
from django.template.loader import render_to_string
from weasyprint import HTML


def recibo_multa_pdf(multa) -> bytes:
    html = render_to_string("prestamos/recibo_multa.html", {"multa": multa})
    return HTML(string=html, base_url=settings.SITE_URL).write_pdf()
