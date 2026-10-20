"""Ejercicio del módulo 28: idioma por petición, emails en el idioma del socio y zonas horarias."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import time_machine
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone, translation

from catalogo.models import Ejemplar, Libro
from core.middleware import zona_horaria_middleware
from prestamos.emails import enviar_recordatorio
from prestamos.models import Prestamo
from prestamos.services import EjemplarNoDisponible, prestar
from usuarios.models import Usuario

pytestmark = pytest.mark.django_db
MADRID = ZoneInfo("Europe/Madrid")


@pytest.fixture
def prestamo():
    libro = Libro.objects.create(titulo="Dune", isbn="9788497593793")
    return Prestamo.objects.create(
        ejemplar=Ejemplar.objects.create(libro=libro, codigo="D1", estado="prestado"),
        socio=Usuario.objects.create_user("ana@example.com", nombre="Ana"),
        fecha_limite=timezone.now() + timedelta(days=2),
    )


# ── 1 y 2. El idioma lo elige Accept-Language ──
def test_api_responde_en_el_idioma_pedido(client):
    url = reverse("prestamos:renovar", args=["token-falso"])
    assert client.get(url).json() == {"error": "Enlace no válido"}
    assert client.get(url, headers={"accept-language": "en"}).json() == {"error": "Invalid link"}
    otro = client.get(url, headers={"accept-language": "fr"})  # no lo tenemos: LANGUAGE_CODE
    assert otro.json() == {"error": "Enlace no válido"}


def test_choices_traducidos(client, prestamo):
    client.force_login(prestamo.socio)
    url = reverse("prestamos:detalle", args=[prestamo.pk])
    en = client.get(url, headers={"accept-language": "en-GB,en;q=0.9"}).json()
    assert (en["estado"], en["estado_texto"]) == ("activo", "Active")  # el valor no cambia


def test_errores_de_servicio_traducidos(prestamo):
    with translation.override("en"), pytest.raises(EjemplarNoDisponible) as error:
        prestar(prestamo.ejemplar.pk, prestamo.socio)
    assert str(error.value) == "Copy D1 is not available"


def test_errores_de_la_api_en_el_idioma_del_frontend(bibliotecario):
    """Módulo 59: el build inglés de Angular manda Accept-Language: en. Los títulos de error
    (módulo 38) y los validadores propios (módulo 05) llegan traducidos."""
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(bibliotecario)
    datos = {"titulo": "Dune", "isbn": "123", "autores_ids": []}
    url = "/api/v1/libros/"
    en = client.post(url, datos, format="json", headers={"accept-language": "en"}).json()
    assert en["title"] == "The submitted data is not valid."
    assert en["errors"]["isbn"] == ["The ISBN must have 13 digits."]
    es = client.post(url, datos, format="json").json()
    assert es["title"] == "Los datos enviados no son válidos."


# ── 3. Emails en el idioma del socio ──
def test_recordatorio_en_el_idioma_del_socio(prestamo, mailoutbox):
    socio = prestamo.socio
    antes = translation.get_language()
    enviar_recordatorio(socio, [prestamo])
    socio.idioma = "en"
    enviar_recordatorio(socio, [prestamo])

    es, en = mailoutbox
    assert es.subject == "Tus préstamos vencen pronto"
    assert en.subject == "Your loans are due soon"
    assert "These loans are due soon:" in en.body and "return by" in en.body
    html = en.alternatives[0][0]
    assert '<html lang="en">' in html and "You have 1 loan due soon:" in html
    assert translation.get_language() == antes  # override restaura el idioma al salir


# ── 4. La trampa de __date a medianoche ──
def test_prestamo_de_las_0030_es_de_hoy_en_madrid(prestamo):
    a_las_0030 = datetime(2026, 3, 10, 0, 30, tzinfo=MADRID)  # = 9 de marzo, 23:30 UTC
    Prestamo.objects.filter(pk=prestamo.pk).update(fecha_inicio=a_las_0030)

    with time_machine.travel(datetime(2026, 3, 10, 0, 45, tzinfo=MADRID), tick=False):
        # ❌ sin zona activa y con TIME_ZONE = "UTC" (el valor de startproject), es día 9
        with timezone.override(ZoneInfo("UTC")):
            hoy_utc = timezone.localdate()
            assert Prestamo.objects.filter(fecha_inicio__date=hoy_utc).count() == 1  # ¡del día 9!

        # ✅ con la zona del usuario activada, "hoy" es el 10 y el préstamo cuenta
        with timezone.override(MADRID):
            hoy = timezone.localdate()
            assert hoy == date(2026, 3, 10)
            assert Prestamo.objects.filter(fecha_inicio__date=hoy).count() == 1
            inicio = timezone.make_aware(datetime.combine(hoy, datetime.min.time()))
            rango = Prestamo.objects.filter(
                fecha_inicio__gte=inicio, fecha_inicio__lt=inicio + timedelta(days=1)
            )
            assert rango.count() == 1  # lo mismo con un rango (aprovecha índices)


def test_date_today_no_es_el_hoy_del_usuario():
    """Django fija la zona del proceso a TIME_ZONE (Madrid): date.today() es el día de Madrid."""
    tokio = ZoneInfo("Asia/Tokyo")
    # .timestamp(): con un datetime con zona, time_machine cambiaría también la zona del proceso
    with time_machine.travel(datetime(2026, 3, 10, 0, 30, tzinfo=tokio).timestamp(), tick=False):
        assert date.today() == date(2026, 3, 9)  # ❌ en Madrid aún son las 16:30 del día 9
        with timezone.override(tokio):
            assert timezone.localdate() == date(2026, 3, 10)  # ✅ el "hoy" del usuario


# ── El middleware de zona horaria ──
@pytest.mark.parametrize(
    ("cabecera", "esperada"),
    [
        ("America/Bogota", "America/Bogota"),
        ("Marte/Olympus", "Europe/Madrid"),
        (None, "Europe/Madrid"),
    ],
)
def test_middleware_zona_horaria(cabecera, esperada):
    vista = zona_horaria_middleware(lambda r: HttpResponse(timezone.get_current_timezone_name()))
    peticion = RequestFactory().get("/", headers={"x-timezone": cabecera} if cabecera else {})
    peticion.user = AnonymousUser()
    assert vista(peticion).content.decode() == esperada  # inválida → TIME_ZONE por defecto
