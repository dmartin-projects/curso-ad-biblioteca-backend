from django.apps import AppConfig


class PrestamosConfig(AppConfig):
    name = "prestamos"

    def ready(self):
        from . import receptores  # noqa: F401
