# test_mensajeria.py
"""Contra un RabbitMQ de verdad (módulo 26, Parte C): docker run -p 5672:5672 rabbitmq:4.2-alpine"""

import threading
import time

import pytest
from kombu import Connection, Producer

from mensajeria import topologia
from mensajeria.consumidor import Consumidor
from mensajeria.publicar import publicar

URL = "amqp://guest:guest@localhost:5672//"


def rabbit_disponible() -> bool:
    try:
        with Connection(URL, connect_timeout=1) as c:
            c.ensure_connection(max_retries=1)
        return True
    except Exception:  # sin broker: kombu lanza OperationalError (o el error de socket)
        return False


# sin RabbitMQ la suite completa sigue en verde: estos tests se saltan con su motivo
pytestmark = pytest.mark.skipif(not rabbit_disponible(), reason="docker compose up -d rabbitmq")


@pytest.fixture
def conexion():
    with Connection(URL) as c:
        canal = c.default_channel
        for cola in topologia.TODAS:  # cada test empieza con las colas vacías
            cola(canal).delete()
        topologia.declarar(c)
        yield c


def vaciar(conexion, cola) -> list:
    mensajes = []
    while (m := cola(conexion.default_channel).get(no_ack=True)) is not None:
        mensajes.append(m)
    return mensajes


@pytest.fixture
def consumir(conexion):
    hilos = []

    def arrancar(manejar):
        c = Consumidor(Connection(URL), topologia.NOTIFICACIONES, manejar, prefetch=5)
        hilo = threading.Thread(target=c.run, daemon=True)
        hilo.start()
        hilos.append((c, hilo))
        return c

    yield arrancar
    for c, hilo in hilos:
        c.should_stop = True
        hilo.join(5)


def esperar(condicion, segundos=15):
    fin = time.monotonic() + segundos
    while time.monotonic() < fin:
        if condicion():
            return
        time.sleep(0.1)
    raise AssertionError("no se cumplió a tiempo")


def test_topic_cada_cola_recibe_lo_suyo(conexion):
    publicar("prestamo.creado", {"id": 1}, url=URL)
    publicar("socio.alta", {"id": 7}, url=URL)
    assert [m.payload["tipo"] for m in vaciar(conexion, topologia.NOTIFICACIONES)] == [
        "prestamo.creado"
    ]
    assert sorted(m.payload["tipo"] for m in vaciar(conexion, topologia.ANALITICA)) == [
        "prestamo.creado",
        "socio.alta",
    ]


def test_falla_dos_veces_y_a_la_tercera_va_sin_duplicar_en_otras_colas(conexion, consumir):
    llamadas = []

    def manejar(evento):
        llamadas.append(time.monotonic())
        if len(llamadas) < 3:
            raise ConnectionError("el servicio de correo no responde")

    consumir(manejar)
    publicar("prestamo.creado", {"id": 1}, url=URL)
    esperar(lambda: len(llamadas) == 3)
    time.sleep(0.5)
    assert len(llamadas) == 3
    assert (
        llamadas[2] - llamadas[0] >= 2 * topologia.ESPERA_REINTENTO_MS / 1000 * 0.9
    )  # esperó en .reintento
    assert (
        len(vaciar(conexion, topologia.ANALITICA)) == 1
    )  # los reintentos NO vuelven a pasar por el topic
    assert vaciar(conexion, topologia.APARCADOS_COLA) == []


def test_siempre_falla_acaba_aparcado_con_su_id_y_sus_intentos(conexion, consumir):
    llamadas = []

    def manejar(evento):
        llamadas.append(1)
        raise ValueError("datos imposibles")

    consumir(manejar)
    id_evento = publicar("prestamo.devuelto", {"id": 3}, url=URL)
    aparcados = []
    esperar(
        lambda: aparcados.extend(vaciar(conexion, topologia.APARCADOS_COLA)) or aparcados,
        segundos=20,
    )
    [m] = aparcados
    assert len(llamadas) == topologia.MAX_INTENTOS
    assert m.properties["message_id"] == id_evento
    assert m.headers["intentos"] == topologia.MAX_INTENTOS


def test_entrega_duplicada_se_procesa_una_vez(conexion, consumir):
    llamadas = []
    c = consumir(llamadas.append)
    producer = Producer(conexion.default_channel)
    for _ in range(2):  # el mismo evento dos veces (p. ej., el publicador reintentó tras un corte)
        producer.publish(
            {"tipo": "prestamo.creado", "datos": {}},
            exchange=topologia.EVENTOS,
            routing_key="prestamo.creado",
            message_id="evento-repetido",
            serializer="json",
        )
    esperar(lambda: "evento-repetido" in c.vistos)
    time.sleep(0.5)
    assert len(llamadas) == 1


def test_un_mensaje_sin_confirmar_vuelve_si_el_consumidor_muere(conexion):
    publicar("prestamo.creado", {"id": 4}, url=URL)
    with Connection(URL) as otra:  # un consumidor que recibe y "muere" sin ack (cierra la conexión)
        m = topologia.NOTIFICACIONES(otra.default_channel).get(no_ack=False)
        assert m is not None
    [vuelto] = vaciar(conexion, topologia.NOTIFICACIONES)
    assert vuelto.payload["datos"] == {"id": 4}
    assert vuelto.delivery_info["redelivered"] is True
