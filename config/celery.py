# config/celery.py
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")  # lee los ajustes CELERY_*
app.autodiscover_tasks()  # busca tasks.py en cada app
