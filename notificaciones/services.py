# notificaciones/services.py
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def notificar_usuario(usuario_id: int, datos: dict) -> None:
    async_to_sync(get_channel_layer().group_send)(
        f"usuario_{usuario_id}",
        {"type": "notificacion.nueva", "datos": datos},  # type → método del consumer
    )


def notificar_bibliotecarios(datos: dict) -> None:
    async_to_sync(get_channel_layer().group_send)(
        "bibliotecarios",
        {"type": "notificacion.nueva", "datos": datos},
    )
