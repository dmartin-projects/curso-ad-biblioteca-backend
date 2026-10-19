"""Ejercicio del módulo 25: consumer con grupos, autenticación por sesión y avisos."""

import pytest
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import Group
from django.test import Client
from django.utils import timezone

from catalogo.models import Ejemplar, Libro
from config.asgi import application
from prestamos.models import Prestamo
from prestamos.services import devolver
from usuarios.models import Usuario

# transaction=True: el consumer consulta la BD desde otro hilo, que no ve una transacción abierta.
# serialized_rollback=True: al acabar, la BD se vacía (TRUNCATE) y esto restaura lo que crearon las
# migraciones de datos (grupos, géneros); sin ello, los tests siguientes no los encontrarían.
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]
ORIGEN = (b"origin", b"http://localhost")


@database_sync_to_async  # como sync_to_async, pero cierra la conexión a la BD al acabar
def cookie_de_sesion(email: str, grupo: str | None = None) -> tuple[bytes, bytes]:
    usuario = Usuario.objects.create_user(email)
    if grupo:
        usuario.groups.add(Group.objects.get(name=grupo))
    client = Client()
    client.force_login(usuario)
    return (b"cookie", f"sessionid={client.cookies['sessionid'].value}".encode())


async def conectar(*cabeceras) -> WebsocketCommunicator:
    ws = WebsocketCommunicator(application, "/ws/notificaciones/", headers=[ORIGEN, *cabeceras])
    conectado, _ = await ws.connect()
    assert conectado
    return ws


async def test_rechaza_anonimo():
    ws = await conectar()
    assert await ws.receive_output() == {"type": "websocket.close", "code": 4401}


async def test_rechaza_origen_ajeno():
    ws = WebsocketCommunicator(
        application, "/ws/notificaciones/", headers=[(b"origin", b"https://malo.example")]
    )
    conectado, _ = await ws.connect()
    assert not conectado  # AllowedHostsOriginValidator: el handshake ni se acepta


async def test_recibe_notificacion_de_su_grupo():
    ana = await conectar(await cookie_de_sesion("ana@example.com"))
    assert await ana.receive_json_from() == {"tipo": "conectado"}
    ana_id = await Usuario.objects.values_list("pk", flat=True).aget(email="ana@example.com")

    await get_channel_layer().group_send(
        f"usuario_{ana_id}", {"type": "notificacion.nueva", "datos": {"x": 1}}
    )
    assert await ana.receive_json_from() == {"tipo": "notificacion", "datos": {"x": 1}}

    await ana.send_json_to({"accion": "ping"})
    assert await ana.receive_json_from() == {"tipo": "pong"}

    await get_channel_layer().group_send(
        "bibliotecarios", {"type": "notificacion.nueva", "datos": {"solo": "personal"}}
    )
    assert await ana.receive_nothing()  # un socio no está en el grupo de bibliotecarios
    await ana.disconnect()


@database_sync_to_async
def devolver_un_prestamo() -> Prestamo:
    libro = Libro.objects.create(titulo="Dune", isbn="9788497593793")
    prestamo = Prestamo.objects.create(
        ejemplar=Ejemplar.objects.create(libro=libro, codigo="D1"),
        socio=Usuario.objects.create_user("luis@example.com"),
        fecha_limite=timezone.now() + Prestamo.DURACION,
    )
    return devolver(prestamo)  # atomic → al confirmar se ejecuta el on_commit


async def test_devolucion_avisa_a_bibliotecarios():
    bibliotecaria = await conectar(await cookie_de_sesion("bea@example.com", "bibliotecarios"))
    socia = await conectar(await cookie_de_sesion("ana@example.com"))
    await bibliotecaria.receive_json_from()
    await socia.receive_json_from()

    prestamo = await devolver_un_prestamo()

    assert await bibliotecaria.receive_json_from() == {
        "tipo": "notificacion",
        "datos": {
            "evento": "prestamo_devuelto",
            "prestamo_id": prestamo.pk,
            "mensaje": "Devuelto «Dune» (D1)",
        },
    }
    assert await socia.receive_nothing()
    await bibliotecaria.disconnect()
    await socia.disconnect()
