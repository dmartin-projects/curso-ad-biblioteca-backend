from .base import *  # noqa: F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # tests mucho más rápidos
MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}  # mail.outbox
