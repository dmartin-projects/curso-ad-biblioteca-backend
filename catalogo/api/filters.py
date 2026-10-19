# catalogo/api/filters.py
import django_filters
from django.db.models import Q

from catalogo.models import Ejemplar, Genero, Libro


class LibroFilter(django_filters.FilterSet):
    titulo = django_filters.CharFilter(lookup_expr="icontains")
    autor = django_filters.CharFilter(field_name="autores__slug")  # ?autor=frank-herbert
    genero = django_filters.ModelMultipleChoiceFilter(  # ?genero=3&genero=5
        field_name="generos",
        queryset=Genero.objects.all(),
        conjoined=False,  # False = OR, True = AND
    )
    publicado_desde = django_filters.DateFilter(field_name="publicado", lookup_expr="gte")
    publicado_hasta = django_filters.DateFilter(field_name="publicado", lookup_expr="lte")
    paginas = django_filters.RangeFilter()  # ?paginas_min=100&paginas_max=300
    disponible = django_filters.BooleanFilter(method="filtrar_disponible")  # ?disponible=true

    class Meta:
        model = Libro
        fields = [
            "titulo",
            "autor",
            "genero",
            "publicado_desde",
            "publicado_hasta",
            "paginas",
            "disponible",
        ]

    def filtrar_disponible(self, queryset, name, valor):
        hay = Q(ejemplares__estado=Ejemplar.Estado.DISPONIBLE)
        return queryset.filter(hay).distinct() if valor else queryset.exclude(hay)
