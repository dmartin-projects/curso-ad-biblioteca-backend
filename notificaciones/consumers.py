# notificaciones/consumers.py
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer


class NotificacionesConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope["user"]  # lo pone el middleware de autenticación
        if not user.is_authenticated:
            await self.accept()  # aceptar y cerrar: ver la nota de abajo
            await self.close(code=4401)  # códigos 4000-4999: propios de la app
            return

        self.grupo_usuario = f"usuario_{user.pk}"
        await self.channel_layer.group_add(self.grupo_usuario, self.channel_name)
        if await self._es_bibliotecario(user):
            await self.channel_layer.group_add("bibliotecarios", self.channel_name)
            self.grupos = [self.grupo_usuario, "bibliotecarios"]
        else:
            self.grupos = [self.grupo_usuario]

        await self.accept()
        await self.send_json({"tipo": "conectado"})

    async def disconnect(self, code):
        for grupo in getattr(self, "grupos", []):
            await self.channel_layer.group_discard(grupo, self.channel_name)

    async def receive_json(self, contenido, **kwargs):
        # Mensajes del cliente al servidor (por ejemplo, marcar una notificación como leída)
        if contenido.get("accion") == "ping":
            await self.send_json({"tipo": "pong"})

    # ── Manejadores de mensajes que llegan desde la channel layer ──
    # El "type" del mensaje ("notificacion.nueva") se convierte en el método notificacion_nueva
    async def notificacion_nueva(self, evento):
        await self.send_json({"tipo": "notificacion", "datos": evento["datos"]})

    @staticmethod
    async def _es_bibliotecario(user):
        # el mismo criterio que PrestamosVisiblesMixin (módulo 14): bibliotecarios, responsables y superusuarios
        return await database_sync_to_async(user.has_perm)("prestamos.view_prestamo")
