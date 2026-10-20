"""Módulo 67: calcular_multas avisa a Healthchecks.io solo si termina bien."""

import httpx
import pytest
import respx

from prestamos import tasks

pytestmark = pytest.mark.django_db
URL = "https://hc-ping.com/1234-abcd"


@respx.mock
def test_avisa_al_terminar(settings):
    settings.HEALTHCHECK_MULTAS_URL = URL
    ping = respx.get(URL).respond(200)
    tasks.calcular_multas()
    assert ping.call_count == 1


@respx.mock
def test_no_avisa_si_la_tarea_falla(settings, monkeypatch):
    settings.HEALTHCHECK_MULTAS_URL = URL
    ping = respx.get(URL).respond(200)

    def rota(*a, **k):
        raise RuntimeError("BD caída")

    monkeypatch.setattr(tasks.Prestamo.objects, "vencidos", rota)
    with pytest.raises(RuntimeError):
        tasks.calcular_multas()
    assert ping.call_count == 0  # sin ping, Healthchecks.io avisará


@respx.mock
def test_si_healthchecks_no_responde_la_tarea_no_falla(settings, caplog):
    settings.HEALTHCHECK_MULTAS_URL = URL
    respx.get(URL).mock(side_effect=httpx.ConnectTimeout("timeout"))
    assert tasks.calcular_multas() == 0
    assert "No se pudo avisar a Healthchecks.io" in caplog.text


def test_sin_url_no_hace_nada(settings):
    settings.HEALTHCHECK_MULTAS_URL = ""
    tasks.calcular_multas()  # sin respx: si intentara salir a la red, fallaría
