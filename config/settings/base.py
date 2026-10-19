from pathlib import Path

import environ

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
THIRD_PARTY_APPS: list[str] = []
LOCAL_APPS = [
    "core",
    "usuarios",
    "catalogo",
    "prestamos",
    "notificaciones",
]
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "core.middleware.RequestIdMiddleware",  # lo primero: el id existe para todo lo demás
    "core.middleware.TiempoRespuestaMiddleware",  # y mide la petición completa
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # justo después de Security
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
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

LANGUAGE_CODE = "es-es"
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
