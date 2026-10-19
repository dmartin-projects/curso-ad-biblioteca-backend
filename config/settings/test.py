from .base import *  # noqa: F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # tests mucho más rápidos
MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}  # mail.outbox

# Los tests no tocan MinIO: los archivos van a memoria. Los estáticos, sin manifiesto
# (si no, cualquier {% static %} exige haber ejecutado collectstatic).
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
WHITENOISE_AUTOREFRESH = True  # busca los estáticos en las apps: no exige collectstatic

# Caché en memoria del proceso: los tests no dependen de Redis (conftest la vacía en cada test)
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
# Sin conexiones persistentes: los hilos de Channels/async no dejan conexiones abiertas
# que impidan borrar la BD de test al terminar
DATABASES["default"]["CONN_MAX_AGE"] = 0  # noqa: F405

# Tareas: en tests se ejecutan en el momento (mismas colas que en base.py, o fallan al importar)
TASKS = {
    "default": {
        "BACKEND": "django.tasks.backends.immediate.ImmediateBackend",
        "QUEUES": ["default", "emails"],
    }
}
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_RESULT_BACKEND = "cache+memory://"  # los chords necesitan un result backend; sin Redis
