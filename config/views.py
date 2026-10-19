# config/views.py
from django.db import connection
from django.db.utils import OperationalError
from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def health(request):
    try:
        connection.ensure_connection()
    except OperationalError:
        return JsonResponse({"status": "db_unavailable"}, status=503)
    return JsonResponse({"status": "ok"})
