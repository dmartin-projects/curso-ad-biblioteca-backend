from django.db import migrations


def separar(apps, schema_editor):
    # ⚠️ Usa apps.get_model: el modelo "histórico" tal como era en ESTA migración
    Autor = apps.get_model("catalogo", "Autor")
    autores = list(Autor.objects.all())
    for autor in autores:
        partes = autor.nombre.rsplit(" ", 1)
        if len(partes) == 2:
            autor.nombre, autor.apellidos = partes
    Autor.objects.bulk_update(autores, ["nombre", "apellidos"], batch_size=1000)


def unir(apps, schema_editor):
    Autor = apps.get_model("catalogo", "Autor")
    for autor in Autor.objects.exclude(apellidos=""):
        autor.nombre = f"{autor.nombre} {autor.apellidos}"
        autor.apellidos = ""
        autor.save(update_fields=["nombre", "apellidos"])


class Migration(migrations.Migration):
    dependencies = [("catalogo", "0003_autor_apellidos")]  # la que añadió el campo

    operations = [
        migrations.RunPython(separar, reverse_code=unir),
    ]
