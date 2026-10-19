from .base import *  # noqa: F403

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# Herramientas de desarrollo que nunca deben llegar a producción
INSTALLED_APPS += []  # noqa: F405  (django-debug-toolbar en el módulo 30)

# Emails (módulo 22): consola por defecto; con USAR_MAILPIT=1 en .env, a Mailpit (http://localhost:8025)
if env.bool("USAR_MAILPIT", default=False):  # noqa: F405
    MAILERS = {
        "default": {
            "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
            "OPTIONS": {"host": "localhost", "port": 1025, "timeout": 5},
        }
    }
