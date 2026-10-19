# core/celery_signals.py — propagar el id de petición a las tareas de Celery (módulo 30)
from celery.signals import before_task_publish, task_postrun, task_prerun

from .middleware import request_id_var


@before_task_publish.connect(dispatch_uid="request_id_publicar")
def anadir_request_id(headers=None, **kwargs):
    # Se ejecuta en el proceso que ENCOLA (la petición): viaja en las cabeceras del mensaje
    if headers is not None:
        headers["request_id"] = request_id_var.get()


@task_prerun.connect(dispatch_uid="request_id_ejecutar")
def recuperar_request_id(task=None, **kwargs):
    # Se ejecuta en el worker: las cabeceras propias aparecen como atributos de task.request
    task._request_id_token = request_id_var.set(getattr(task.request, "request_id", None) or "-")


@task_postrun.connect(dispatch_uid="request_id_limpiar")
def limpiar_request_id(task=None, **kwargs):
    token = getattr(task, "_request_id_token", None)
    if token is not None:
        request_id_var.reset(token)  # el siguiente mensaje del mismo proceso no lo hereda
        task._request_id_token = None
