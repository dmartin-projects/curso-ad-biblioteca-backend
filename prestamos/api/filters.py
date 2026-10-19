# prestamos/api/filters.py (módulo 37)
import django_filters
from django.contrib.auth import get_user_model

from core.permissions import es_personal
from prestamos.models import Prestamo

Usuario = get_user_model()


def socios_que_puede_nombrar(request):
    """🔐 Lo que el usuario puede poner en ?socio=: el personal, cualquiera; un socio, solo él."""
    if request is None:  # al generar el esquema OpenAPI
        return Usuario.objects.none()
    if es_personal(request.user):
        return Usuario.objects.all()
    return Usuario.objects.filter(pk=request.user.pk)


class PrestamoFilter(django_filters.FilterSet):
    socio = django_filters.ModelChoiceFilter(queryset=socios_que_puede_nombrar)
    estado = django_filters.ChoiceFilter(choices=Prestamo.Estado.choices)
    desde = django_filters.DateFilter(field_name="fecha_inicio", lookup_expr="date__gte")

    class Meta:
        model = Prestamo
        fields = ["socio", "estado", "desde"]
