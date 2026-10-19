from .base import *  # noqa: F403

DEBUG = False
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")  # noqa: F405  (sin valor por defecto: obligatorio)

# ── HTTPS y cookies (módulo 29) ──
# Solo porque nuestro proxy (Caddy/nginx) SIEMPRE fija esta cabecera, sobrescribiendo la del cliente
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = [r"^health/"]  # los healthchecks internos llegan por HTTP
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
JWT_REFRESH_COOKIE = {**JWT_REFRESH_COOKIE, "secure": True}  # noqa: F405  (por si DEBUG se cuela)
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=3600)  # noqa: F405  (súbelo poco a poco)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])  # noqa: F405

# ── Throttling detrás de Caddy/nginx (módulo 36): la IP real viene en X-Forwarded-For ──
REST_FRAMEWORK = {**REST_FRAMEWORK, "NUM_PROXIES": 1}  # noqa: F405

# ── CORS: solo los orígenes de la configuración ──
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])  # noqa: F405
CORS_ALLOW_CREDENTIALS = True

# ── CSP obligatoria (en desarrollo, solo informa) ──
SECURE_CSP = CSP_POLITICA  # noqa: F405
SECURE_CSP_REPORT_ONLY = {}

# ── Email real: check --deploy falla (mail.E001) si el mailer de producción es de desarrollo ──
MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "OPTIONS": {
            "host": env("SMTP_HOST"),  # noqa: F405
            "port": env.int("SMTP_PORT", default=587),  # noqa: F405
            "username": env("SMTP_USER", default=""),  # noqa: F405
            "password": env("SMTP_PASSWORD", default=""),  # noqa: F405
            "use_tls": True,
            "timeout": 10,
        },
    },
}

# ── Sentry (módulo 30): solo si hay DSN ──
if SENTRY_DSN := env("SENTRY_DSN", default=""):  # noqa: F405
    import sentry_sdk

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=env("ENTORNO", default="produccion"),  # noqa: F405
        release=env("GIT_SHA", default=None),  # noqa: F405
        traces_sample_rate=0.1,
        # Sin datos personales: es el comportamiento por defecto. send_default_pii=False está
        # obsoleto desde sentry-sdk 2.7x; para afinar qué se envía, data_collection={...}
    )
