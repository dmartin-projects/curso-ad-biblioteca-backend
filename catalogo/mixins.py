from django.http import JsonResponse

from .models import Libro


class JSONResponseMixin:
    """Sustituye el renderizado de plantillas por JSON."""

    def render_to_response(self, context, **response_kwargs):
        return JsonResponse(self.get_data(context), **response_kwargs)

    def get_data(self, context):
        raise NotImplementedError


class FiltrosLibroMixin:
    def get_queryset(self):
        qs = Libro.objects.select_related("autor").order_by("titulo")
        params = self.request.GET
        if q := params.get("q"):
            qs = qs.filter(titulo__icontains=q)
        if autor := params.get("autor"):
            qs = qs.filter(autor__slug=autor)
        if (desde := params.get("desde")) and desde.isdigit():
            qs = qs.filter(publicado__year__gte=int(desde))
        return qs
