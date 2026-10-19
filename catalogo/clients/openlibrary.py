# catalogo/clients/openlibrary.py
import logging
from dataclasses import dataclass

import httpx
from django.conf import settings
from django.core.cache import cache
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter

logger = logging.getLogger(__name__)


class OpenLibraryError(Exception):
    """Error al hablar con Open Library (el resto del código solo conoce esta excepción)."""


@dataclass(frozen=True)
class DatosLibro:
    isbn: str
    titulo: str
    autores: list[str]
    paginas: int | None
    anio: int | None


def _es_transitorio(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in {
        429,
        502,
        503,
        504,
    }


class OpenLibraryClient:
    def __init__(self, http: httpx.Client | None = None):
        self.http = http or httpx.Client(
            base_url=settings.OPENLIBRARY_URL,
            timeout=httpx.Timeout(8.0, connect=3.0),
            headers={"User-Agent": settings.HTTP_USER_AGENT},
        )

    @retry(
        retry=retry_if_exception(_es_transitorio),
        wait=wait_exponential_jitter(multiplier=0.5, max=8),  # 0,5 s, 1 s, 2 s… + jitter
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _get(self, ruta: str, **params) -> dict:
        r = self.http.get(ruta, params=params)
        r.raise_for_status()
        return r.json()

    def buscar_isbn(self, isbn: str) -> DatosLibro | None:
        clave = f"openlibrary:isbn:{isbn}"
        if (en_cache := cache.get(clave)) is not None:
            return en_cache or None  # {} = "sabemos que no existe"
        try:
            datos = self._get(f"/isbn/{isbn}.json")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                cache.set(clave, {}, timeout=60 * 60 * 24)  # caché negativa
                return None
            raise OpenLibraryError(f"Open Library respondió {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise OpenLibraryError("Open Library no responde") from exc

        libro = self._parsear(isbn, datos)
        cache.set(clave, libro, timeout=60 * 60 * 24 * 7)
        return libro

    @staticmethod
    def _parsear(isbn: str, datos: dict) -> DatosLibro:
        # Valida y normaliza: no confíes en que los campos existan
        anio = None
        if fecha := datos.get("publish_date"):
            digitos = "".join(c for c in fecha if c.isdigit())[-4:]
            anio = int(digitos) if len(digitos) == 4 else None
        return DatosLibro(
            isbn=isbn,
            titulo=str(datos.get("title", "")).strip()[:300],
            autores=[a.get("key", "") for a in datos.get("authors", [])],
            paginas=datos.get("number_of_pages")
            if isinstance(datos.get("number_of_pages"), int)
            else None,
            anio=anio,
        )
