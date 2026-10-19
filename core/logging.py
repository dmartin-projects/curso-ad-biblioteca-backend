# core/logging.py — el id de petición en cada línea de log (módulo 30)
import logging

from .middleware import request_id_var  # lo fija RequestIdMiddleware (módulo 16)


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_var.get()
        return True
