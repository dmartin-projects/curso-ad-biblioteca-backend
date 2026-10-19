# core/circuit_breaker.py
from django.core.cache import cache


class CircuitoAbierto(Exception):
    pass


class CircuitBreaker:
    """CLOSED → (umbral fallos seguidos) → OPEN → (enfriamiento) → HALF-OPEN: una sola llamada de prueba.

    El estado vive en la caché (Redis), así que lo comparten todos los procesos.
    """

    def __init__(self, nombre: str, umbral: int = 5, enfriamiento: int = 60):
        self.clave_fallos = f"cb:{nombre}:fallos"
        self.clave_abierto = f"cb:{nombre}:abierto"  # existe mientras está abierto (TTL)
        self.clave_por_probar = f"cb:{nombre}:por_probar"  # se abrió y aún no ha vuelto a cerrar
        self.clave_probando = f"cb:{nombre}:probando"  # la llamada de prueba en curso
        self.umbral, self.enfriamiento = umbral, enfriamiento

    def llamar(self, funcion, *args, **kwargs):
        if cache.get(self.clave_abierto):
            raise CircuitoAbierto(self.clave_abierto)
        semiabierto = bool(cache.get(self.clave_por_probar))
        # cache.add es atómico: de todas las llamadas que llegan a la vez, solo una prueba
        if semiabierto and not cache.add(self.clave_probando, True, timeout=self.enfriamiento):
            raise CircuitoAbierto(self.clave_probando)
        try:
            resultado = funcion(*args, **kwargs)
        except Exception:
            if semiabierto:
                self._abrir()  # la prueba falla: abierto otra vez, sin esperar a `umbral` fallos
                raise
            cache.add(
                self.clave_fallos, 0, timeout=self.enfriamiento
            )  # crea el contador si no existe
            fallos = cache.incr(self.clave_fallos)  # incremento atómico en Redis
            if fallos >= self.umbral:
                self._abrir()
            raise
        cache.delete_many([self.clave_fallos, self.clave_por_probar, self.clave_probando])  # cierra
        return resultado

    def _abrir(self):
        cache.set(self.clave_abierto, True, timeout=self.enfriamiento)
        cache.set(self.clave_por_probar, True, timeout=None)  # al caducar 'abierto': semiabierto
        cache.delete_many([self.clave_fallos, self.clave_probando])


breaker_ia = CircuitBreaker("ia", umbral=5, enfriamiento=120)
