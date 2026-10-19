from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "core"

    def ready(self):
        from . import lookups  # noqa: F401  ← registra los lookups al arrancar
