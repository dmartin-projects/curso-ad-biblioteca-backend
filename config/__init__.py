# config/__init__.py — carga Celery con Django, para que @shared_task use esta app
from .celery import app as celery_app

__all__ = ("celery_app",)
