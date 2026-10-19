from django.contrib.postgres.operations import TrigramExtension, UnaccentExtension
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("catalogo", "0006_libro_metadatos_etiquetas_busqueda")]
    operations = [TrigramExtension(), UnaccentExtension()]
