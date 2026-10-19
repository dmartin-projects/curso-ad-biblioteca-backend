from .base import *  # noqa: F403

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# Herramientas de desarrollo que nunca deben llegar a producción
# Módulo 30. USAR_SILK=0 para desactivarlo: silk guarda CADA petición en la BD (sin BD, nada responde)
if env.bool("USAR_SILK", default=True):  # noqa: F405
    INSTALLED_APPS += ["debug_toolbar", "silk"]  # noqa: F405
    MIDDLEWARE = [  # noqa: F405
        "debug_toolbar.middleware.DebugToolbarMiddleware",
        "silk.middleware.SilkyMiddleware",
        *MIDDLEWARE,  # noqa: F405
    ]
    INTERNAL_IPS = ["127.0.0.1"]

# Emails (módulo 22): consola por defecto; con USAR_MAILPIT=1 en .env, a Mailpit (http://localhost:8025)
if env.bool("USAR_MAILPIT", default=False):  # noqa: F405
    MAILERS = {
        "default": {
            "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
            "OPTIONS": {"host": "localhost", "port": 1025, "timeout": 5},
        }
    }

# La API navegable, solo en desarrollo (módulo 32)
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [  # noqa: F405
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
]
