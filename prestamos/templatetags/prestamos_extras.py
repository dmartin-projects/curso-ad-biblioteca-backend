# prestamos/templatetags/prestamos_extras.py
from django import template
from django.utils import timezone
from django.utils.translation import gettext as _

register = template.Library()


@register.filter
def euros(valor):
    """{{ multa.total|euros }} → '2,50 €'"""
    if valor is None:
        return "—"
    return f"{valor:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


@register.filter
def dias_restantes(fecha):
    return (fecha - timezone.now()).days


@register.simple_tag(takes_context=True)
def saludo(context):
    hora = timezone.localtime().hour
    return _("Buenos días") if hora < 14 else _("Buenas tardes")


@register.inclusion_tag("prestamos/_resumen.html")
def resumen_prestamos(socio):
    activos = socio.prestamos.filter(estado="activo").select_related("ejemplar__libro")
    return {"activos": activos}
