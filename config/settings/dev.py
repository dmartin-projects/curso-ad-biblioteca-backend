from .base import *  # noqa: F403

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# Herramientas de desarrollo que nunca deben llegar a producción
INSTALLED_APPS += []  # noqa: F405  (django-debug-toolbar en el módulo 30)
