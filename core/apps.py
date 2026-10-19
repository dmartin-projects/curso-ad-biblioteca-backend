from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "core"

    def ready(self):
        from . import celery_signals, lookups  # noqa: F401  ← registran lookups y signals al arrancar
