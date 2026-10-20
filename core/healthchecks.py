"""Módulo 67: "dead man's switch" con Healthchecks.io. Una tarea periódica avisa de que ha
TERMINADO BIEN; si el aviso no llega a su hora, Healthchecks.io te escribe."""

import logging

import httpx

logger = logging.getLogger(__name__)


def avisar_healthchecks(url: str) -> None:
    """Hace el ping. Nunca rompe la tarea: si Healthchecks.io no responde, solo queda en el log
    (y, como no le llegó el ping, avisará él)."""
    if not url:
        return  # desarrollo y tests: sin URL configurada, nada
    try:
        httpx.get(url, timeout=5).raise_for_status()
    except httpx.HTTPError as e:
        logger.warning("No se pudo avisar a Healthchecks.io: %s", e)
