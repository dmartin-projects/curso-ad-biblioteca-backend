# conftest.py — fixtures compartidas por todos los tests
import pytest
from django.conf import settings
from django.core.cache import cache
from django.utils import translation

from usuarios.tests.factories import UsuarioFactory


@pytest.fixture(autouse=True)
def idioma_por_defecto():
    """Una petición con Accept-Language deja el idioma activado en el hilo (módulo 28)."""
    translation.activate(settings.LANGUAGE_CODE)
    yield
    translation.activate(settings.LANGUAGE_CODE)


@pytest.fixture(autouse=True)
def cache_limpia():
    """Cada test empieza con la caché vacía (módulo 23): sin esto, un test ve lo que dejó otro."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def celery_sin_propagar(settings):
    """Para probar reintentos en modo eager (módulo 26).

    Con CELERY_TASK_EAGER_PROPAGATES, el primer self.retry() sale como excepción Retry.
    Sin propagar, apply() encadena los reintentos en el momento (sin esperar el backoff).
    Celery lee los CELERY_* de los settings de Django al consultarlos: basta con cambiarlos aquí.
    """
    settings.CELERY_TASK_EAGER_PROPAGATES = False


@pytest.fixture
def socio(db):  # `db` activa el acceso a la BD (módulo 31)
    return UsuarioFactory()


@pytest.fixture
def bibliotecario(db):
    return UsuarioFactory(bibliotecario=True)
