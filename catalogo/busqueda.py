from django.contrib.postgres.search import SearchVector
from django.db.models import Value

from .models import Libro


def actualizar_busqueda(libro_id: int) -> None:
    """Recalcula el vector de un libro: título (A), autores (B) y sinopsis (C)."""
    nombres = " ".join(
        Libro.autores.through.objects.filter(libro_id=libro_id).values_list(
            "autor__nombre", flat=True
        )
    )
    vector = (
        SearchVector("titulo", weight="A", config="spanish")
        + SearchVector(Value(nombres), weight="B", config="spanish")
        + SearchVector("sinopsis", weight="C", config="spanish")
    )
    # update(): no vuelve a emitir post_save (llamar a save() aquí sería un bucle infinito)
    Libro.objects.filter(pk=libro_id).update(busqueda=vector)
