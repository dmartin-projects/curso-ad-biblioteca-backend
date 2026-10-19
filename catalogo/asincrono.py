# catalogo/asincrono.py — vistas asíncronas (módulo 24)
import asyncio

import httpx
from django.http import JsonResponse

from .models import Libro

OPENLIBRARY = "https://openlibrary.org/isbn/{isbn}.json"
GOOGLE_BOOKS = "https://www.googleapis.com/books/v1/volumes"
PORTADA = "https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg"


def _peticiones(client: httpx.AsyncClient, isbn: str):
    return [
        client.get(OPENLIBRARY.format(isbn=isbn)),
        client.get(GOOGLE_BOOKS, params={"q": f"isbn:{isbn}"}),
        client.head(PORTADA.format(isbn=isbn)),
    ]


def _respuesta(isbn, libro, openlib, google, portada) -> JsonResponse:
    def ok(r):
        return isinstance(r, httpx.Response) and r.is_success

    return JsonResponse(
        {
            "isbn": isbn,
            "en_catalogo": libro is not None,
            "openlibrary": openlib.json() if ok(openlib) else None,
            "google_books": google.json().get("totalItems", 0) if ok(google) else None,
            "tiene_portada": ok(portada),
        }
    )


async def info_libro(request, isbn: str):
    async with httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
        # Tres llamadas EN PARALELO: tarda lo que la más lenta, no la suma
        openlib, google, portada = await asyncio.gather(
            *_peticiones(client, isbn),
            return_exceptions=True,  # una que falle no tumba las demás
        )
    libro = await Libro.objects.filter(isbn=isbn).afirst()
    return _respuesta(isbn, libro, openlib, google, portada)


async def info_libro_secuencial(request, isbn: str):
    """Solo para comparar (ejercicio 2): las mismas llamadas, una detrás de otra."""
    resultados = []
    async with httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
        for peticion in _peticiones(client, isbn):
            try:
                resultados.append(await peticion)
            except httpx.HTTPError as error:
                resultados.append(error)
    libro = await Libro.objects.filter(isbn=isbn).afirst()
    return _respuesta(isbn, libro, *resultados)
