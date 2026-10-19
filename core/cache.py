# core/cache.py — utilidades de caché reutilizables (módulo 23)
import time

from django.core.cache import cache


def con_cerrojo(clave: str, calcular, timeout: int = 600, espera: float = 0.1, intentos: int = 50):
    """Cache-aside con cerrojo: si la clave falta, solo UN proceso recalcula; el resto espera."""
    valor = cache.get(clave)
    if valor is not None:
        return valor
    for _ in range(intentos):
        if cache.add(f"lock:{clave}", 1, timeout=30):  # solo uno consigue el cerrojo
            try:
                valor = calcular()
                cache.set(clave, valor, timeout)
            finally:
                cache.delete(f"lock:{clave}")
            return valor
        time.sleep(espera)  # los demás esperan y vuelven a mirar
        valor = cache.get(clave)
        if valor is not None:
            return valor
    return calcular()  # el que tenía el cerrojo murió: no te quedes colgado


def obtener_version(nombre: str) -> int:
    return cache.get_or_set(f"version:{nombre}", 1, timeout=None)


def subir_version(nombre: str) -> None:
    try:
        cache.incr(f"version:{nombre}")  # las claves con la versión antigua quedan inaccesibles
    except ValueError:  # no existía (Redis reiniciado, caché vaciada)
        cache.set(f"version:{nombre}", 1, timeout=None)
