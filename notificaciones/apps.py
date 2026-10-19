from django.apps import AppConfig


class NotificacionesConfig(AppConfig):
    name = "notificaciones"

    def ready(self):
        from . import receptores  # noqa: F401
