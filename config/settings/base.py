from datetime import timedelta
from pathlib import Path

import environ
from celery.schedules import crontab
from django.utils.csp import CSP
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # .../backend

env = environ.Env()
environ.Env.read_env(
    BASE_DIR / ".env"
)  # en producción las variables vienen del sistema, no del archivo

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
]
THIRD_PARTY_APPS = [
    "channels",
    "django_tasks_db",
    "corsheaders",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "rest_framework_simplejwt.token_blacklist",  # módulo 35: lista negra de refresh tokens
]
LOCAL_APPS = [
    "core",
    "usuarios",
    "catalogo",
    "prestamos",
    "notificaciones",
    "tickets",
]
# daphne el primero: runserver pasa a ser ASGI (módulo 25)
INSTALLED_APPS = ["daphne", *DJANGO_APPS, *THIRD_PARTY_APPS, *LOCAL_APPS]

ASGI_APPLICATION = "config.asgi.application"
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        # socket_timeout > 5: con redis-py 8 un WebSocket sin mensajes se cae cada 5 s
        "CONFIG": {
            "hosts": [
                {
                    "address": env("REDIS_CHANNELS_URL", default="redis://localhost:6379/2"),
                    "socket_timeout": 10,
                }
            ]
        },
    },
}

MIDDLEWARE = [
    "core.middleware.RequestIdMiddleware",  # lo primero: el id existe para todo lo demás
    "core.middleware.TiempoRespuestaMiddleware",  # y mide la petición completa
    "corsheaders.middleware.CorsMiddleware",  # lo más arriba posible (responde a los OPTIONS)
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # justo después de Security
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",  # después de sesiones, antes de Common
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.zona_horaria_middleware",  # después de Auth (usa request.user)
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",  # módulo 29
    "core.middleware.MantenimientoMiddleware",
    "core.middleware.PeticionesLentasMiddleware",  # después de Auth (usa request.user)
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.csp",  # {{ csp_nonce }} en plantillas
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": env.db("DATABASE_URL"),
}
DATABASES["default"]["CONN_MAX_AGE"] = env.int(
    "DB_CONN_MAX_AGE", default=60
)  # reutiliza conexiones
# comprueba la conexión antes de reutilizarla: sin esto, tras un reinicio de PostgreSQL la primera
# petición de cada worker falla con OperationalError
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

AUTH_USER_MODEL = "usuarios.Usuario"  # ⚠️ ver sección 5

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es"
LANGUAGES = [("es", _("Español")), ("en", _("Inglés"))]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "Europe/Madrid"
USE_I18N = True
USE_TZ = True  # guarda las fechas en UTC y convierte al mostrarlas

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
# URL pública del backend: enlaces absolutos en emails y base_url de los PDF (módulo 21)
SITE_URL = env("SITE_URL", default="http://localhost:8000")

# ── Archivos (módulo 20) ──
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": env("S3_BUCKET", default="biblioteca"),
            "endpoint_url": env("S3_ENDPOINT_URL", default="http://localhost:9000"),
            "access_key": env("S3_ACCESS_KEY", default="minio"),
            "secret_key": env("S3_SECRET_KEY", default="minio12345"),
            "region_name": "us-east-1",
            "signature_version": "s3v4",  # firma v4: la v2 está obsoleta
            "default_acl": None,
            "querystring_auth": True,
            "querystring_expire": 300,
            "file_overwrite": False,
        },
    },
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
CORS_MEDIA_ORIGENES = env.list("CORS_MEDIA_ORIGENES", default=["http://localhost:4200"])
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2_621_440
DATA_UPLOAD_MAX_NUMBER_FILES = 20

# Desde Django 6.0 el valor por defecto ya es BigAutoField; no hace falta declararlo.

# ── Autenticación (módulo 12) ──
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",  # el preferido
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",  # los que ya existían se leen y se actualizan al entrar
]
AUTHENTICATION_BACKENDS = [
    "usuarios.backends.EmailONumeroSocioBackend",
    "django.contrib.auth.backends.ModelBackend",
    "prestamos.backends.PrestamoPermisosBackend",  # permisos por objeto (módulo 14)
]
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"
PASSWORD_RESET_TIMEOUT = 60 * 60 * 24

# ── Caché (módulo 23) ──
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL", default="redis://localhost:6379/1"),
        "KEY_PREFIX": "biblioteca",
        "TIMEOUT": 300,
    },
}
SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"  # lee de Redis, persiste en la BD

# Emails: de momento se imprimen en la consola de runserver (módulo 22: Mailpit y SMTP)
MAILERS = {"default": {"BACKEND": "django.core.mail.backends.console.EmailBackend"}}
DEFAULT_FROM_EMAIL = '"Biblioteca" <no-responder@biblioteca.example>'
SERVER_EMAIL = "errores@biblioteca.example"


# ── API (módulo 32) ──
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",  # primero: anónimo → 401
        "rest_framework.authentication.SessionAuthentication",  # API navegable / admin
    ],
    # Límites para los endpoints sensibles (módulo 35; se explica en el 36)
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"login": "5/min", "registro": "5/hour", "recuperar": "3/hour"},
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",  # ✅ cerrado por defecto
    ],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.URLPathVersioning",
    "DEFAULT_VERSION": "v1",
    "ALLOWED_VERSIONS": ["v1"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "COERCE_DECIMAL_TO_STRING": True,
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}
# drf-spectacular revisa el esquema en `manage.py check`: las APIView sin serializer dan W002 y
# `check --deploy --fail-level WARNING` (módulo 29) fallaría. Se documentan en el módulo 38.
SILENCED_SYSTEM_CHECKS = ["drf_spectacular.W002"]  # ← quítalo en el módulo 38

# ── JWT (módulo 35) ──
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=10),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": env("JWT_SIGNING_KEY"),  # distinta de SECRET_KEY, ≥ 32 bytes
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_CLAIM": "user_id",
    # el token lleva un hash de la contraseña: al cambiarla, los access ya emitidos dejan de valer
    "CHECK_REVOKE_TOKEN": True,
}
JWT_REFRESH_COOKIE = {
    "key": "refresh",
    "path": "/api/v1/auth/",  # solo viaja a los endpoints de auth
    "httponly": True,
    "secure": not DEBUG,  # en local (http) no puede ser Secure; prod.py lo fuerza
    "samesite": "Strict",
}
FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:4200")  # enlaces de los emails

# ── Seguridad (módulo 29) ──
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=["http://localhost:4200"])
CSP_POLITICA = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF, CSP.NONCE],
    "style-src": [CSP.SELF, CSP.NONCE],
    "img-src": [CSP.SELF, "data:", "https://covers.openlibrary.org"],
    "connect-src": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
    "object-src": [CSP.NONE],
    "base-uri": [CSP.SELF],
}
# En desarrollo, solo informa: el navegador avisa en la consola y envía un informe a /csp-report/
SECURE_CSP_REPORT_ONLY = {**CSP_POLITICA, "report-uri": "/csp-report/"}

# ── Logging (módulo 30) ──
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,  # ⚠️ con True silenciarías los loggers de Django y librerías
    "filters": {"request_id": {"()": "core.logging.RequestIdFilter"}},
    "formatters": {
        "texto": {"format": "{asctime} {levelname} {name} [{request_id}] {message}", "style": "{"},
        "json": {
            "()": "pythonjsonlogger.json.JsonFormatter",
            "fmt": "%(asctime)s %(levelname)s %(name)s %(request_id)s %(message)s",
        },
    },
    "handlers": {
        "consola": {
            "class": "logging.StreamHandler",
            "formatter": env("LOG_FORMAT", default="texto"),  # "json" en producción
            "filters": ["request_id"],
        },
    },
    "root": {"handlers": ["consola"], "level": "INFO"},
    "loggers": {
        "django": {"level": "INFO"},
        "django.db.backends": {"level": env("SQL_LOG_LEVEL", default="WARNING")},
        "celery": {"level": "INFO"},
        "httpx": {"level": "WARNING"},
        "weasyprint": {"level": "WARNING"},  # INFO es muy ruidoso (cada paso del PDF)
        "fontTools": {"level": "WARNING"},
    },
}

# ── APIs externas (módulo 27) ──
OPENLIBRARY_URL = env("OPENLIBRARY_URL", default="https://openlibrary.org")
HTTP_USER_AGENT = env("HTTP_USER_AGENT", default="Biblioteca/1.0 (contacto@biblioteca.example)")

# ── Tareas (módulo 26) ──
# django.tasks: emails sencillos, cola en PostgreSQL (manage.py db_worker)
TASKS = {
    "default": {
        "BACKEND": "django_tasks_db.DatabaseBackend",
        "QUEUES": ["default", "emails"],
    },
}

# Celery: RabbitMQ como broker, Redis para resultados
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="amqp://guest:guest@localhost:5672//")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/0")
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = 300
CELERY_TASK_SOFT_TIME_LIMIT = 270
CELERY_RESULT_EXPIRES = 60 * 60 * 24
CELERY_TASK_TRACK_STARTED = True
CELERY_WORKER_HIJACK_ROOT_LOGGER = False  # el worker usa nuestro LOGGING (con request_id)
CELERY_WORKER_SEND_TASK_EVENTS = True  # sin eventos, Flower ve los workers pero no las tareas
CELERY_TASK_SEND_SENT_EVENT = True
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_ROUTES = {
    "*.tasks.enviar_*": {"queue": "emails"},
    "tickets.tasks.*": {"queue": "ocr"},
}
CELERY_BEAT_SCHEDULE = {
    "calcular-multas": {
        "task": "prestamos.tasks.calcular_multas",
        "schedule": crontab(hour=1, minute=30),  # cada noche
    },
    "recordatorios-diarios": {
        "task": "prestamos.tasks.enviar_recordatorios_vencimiento",
        "schedule": crontab(hour=9, minute=0),
    },
}
