# core/api/exceptions.py
import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import ProtectedError
from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler as handler_drf
from rest_framework.views import set_rollback

from core.exceptions import ErrorDeDominio
from core.logging import request_id_var

logger = logging.getLogger(__name__)

# gettext_lazy: se traducen al responder, según el Accept-Language de cada petición (módulo 28).
TITULOS = {
    400: ("validacion", _("Los datos enviados no son válidos.")),
    401: ("no_autenticado", _("Debes iniciar sesión.")),
    403: ("sin_permiso", _("No tienes permiso para realizar esta acción.")),
    404: ("no_encontrado", _("El recurso no existe.")),
    405: ("metodo_no_permitido", _("Método no permitido.")),
    415: ("tipo_no_soportado", _("Tipo de contenido no soportado.")),
    429: ("limite_peticiones", _("Demasiadas peticiones. Inténtalo más tarde.")),
}


def _aplanar(errores, prefijo=""):
    """{"lineas": {1: {"precio": ["…"]}}} → {"lineas.1.precio": ["…"]}"""
    if isinstance(errores, dict):
        plano = {}
        for clave, valor in errores.items():
            plano.update(_aplanar(valor, f"{prefijo}.{clave}" if prefijo else str(clave)))
        return plano
    if isinstance(errores, list) and errores and isinstance(errores[0], (dict, list)):
        plano = {}
        for i, valor in enumerate(errores):
            if valor:
                plano.update(_aplanar(valor, f"{prefijo}.{i}" if prefijo else str(i)))
        return plano
    lista = errores if isinstance(errores, list) else [errores]
    return {prefijo or "non_field_errors": [str(e) for e in lista]}


def _problema(status_code, tipo, titulo, detail=None, errors=None, headers=None):
    return Response(
        {
            "type": tipo,
            "title": titulo,
            "status": status_code,
            "detail": detail,
            "errors": errors,
            "request_id": request_id_var.get(),
        },
        status=status_code,
        headers=headers,
    )


def manejador_errores(exc, context):
    # Respondemos en vez de dejar subir la excepción: con ATOMIC_REQUESTS, la transacción de la
    # petición se confirmaría con lo que se escribió antes del error. DRF lo evita en su handler
    # con set_rollback(); como devolvemos respuestas propias, lo llamamos aquí, para todas.
    set_rollback()

    # 1. Errores de dominio → su status y código
    if isinstance(exc, ErrorDeDominio):
        return _problema(exc.status, exc.codigo, exc.mensaje, detail=exc.contexto or None)

    # 1b. Borrar algo que otros registros protegen (on_delete=PROTECT): conflicto, no 500
    if isinstance(exc, ProtectedError):
        return _problema(409, "en_uso", _("No se puede borrar: hay registros que dependen de él."))

    # 2. ValidationError de Django (validate_password, full_clean, validadores de modelo) → 400
    if isinstance(exc, DjangoValidationError):
        exc = exceptions.ValidationError(
            exc.message_dict if hasattr(exc, "error_dict") else {"non_field_errors": exc.messages}
        )

    # 3. Lo que DRF ya sabe tratar (APIException, Http404, PermissionDenied)
    respuesta = handler_drf(exc, context)
    if respuesta is None:
        # 4. Cualquier otra cosa: 500 sin detalles internos (el traceback va a logs/Sentry)
        logger.exception("Error no controlado en %s", context["view"].__class__.__name__)
        return _problema(500, "error_interno", _("Ha ocurrido un error inesperado."))

    codigo = respuesta.status_code
    tipo, titulo = TITULOS.get(codigo, ("error", _("Error.")))
    cabeceras = {k: v for k, v in respuesta.items()}  # conserva WWW-Authenticate, Retry-After…
    if isinstance(exc, exceptions.ValidationError):
        return _problema(codigo, tipo, titulo, errors=_aplanar(respuesta.data), headers=cabeceras)
    detalle = respuesta.data.get("detail") if isinstance(respuesta.data, dict) else respuesta.data
    return _problema(
        codigo, tipo, titulo, detail=str(detalle) if detalle else None, headers=cabeceras
    )
