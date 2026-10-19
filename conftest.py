# conftest.py — fixtures compartidas por todos los tests
import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def cache_limpia():
    """Cada test empieza con la caché vacía (módulo 23): sin esto, un test ve lo que dejó otro."""
    cache.clear()
    yield
    cache.clear()
