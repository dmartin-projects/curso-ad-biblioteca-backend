from django.db import migrations

GENEROS = [
    ("Novela", None),
    ("Ensayo", None),
    ("Poesía", None),
    ("Ciencia ficción", "Novela"),
    ("Infantil", None),
]


def crear_generos(apps, schema_editor):
    Genero = apps.get_model("catalogo", "Genero")
    for nombre, padre in GENEROS:
        padre_obj = Genero.objects.get(nombre=padre) if padre else None
        Genero.objects.get_or_create(nombre=nombre, defaults={"padre": padre_obj})


def borrar_generos(apps, schema_editor):
    Genero = apps.get_model("catalogo", "Genero")
    # al revés: primero los hijos (padre usa PROTECT) y solo los que no tengan libros
    for nombre, _ in reversed(GENEROS):
        Genero.objects.filter(nombre=nombre, libros__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [("catalogo", "0004_separar_apellidos")]
    operations = [migrations.RunPython(crear_generos, reverse_code=borrar_generos)]
