from .base import *  # noqa: F403

DEBUG = False
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")  # noqa: F405  (sin valor por defecto: obligatorio)

# ── HTTPS y cookies (módulo 29) ──
# Solo porque nuestro proxy (Caddy/nginx) SIEMPRE fija esta cabecera, sobrescribiendo la del cliente
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = [r"^health/$"]  # el healthcheck interno llega por HTTP
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=3600)  # noqa: F405  (súbelo poco a poco)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])  # noqa: F405

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
