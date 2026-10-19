from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from catalogo.servicios_importacion import importar_libros, leer_csv


class Command(BaseCommand):
    help = "Importa libros desde un CSV (titulo;isbn;autor;publicado). Todo o nada."

    def add_arguments(self, parser):
        parser.add_argument("ruta", type=Path, help="Ruta del CSV")
        parser.add_argument("--delimitador", default=";")
        parser.add_argument("--dry-run", action="store_true", help="Valida y simula sin guardar")

    def handle(self, *args, ruta: Path, delimitador: str, dry_run: bool, **options):
        if not ruta.exists():
            raise CommandError(f"No existe el archivo {ruta}")  # sale con código 1
        resultado = importar_libros(leer_csv(ruta, delimitador), guardar=not dry_run)
        if resultado.errores:
            for error in resultado.errores:
                self.stderr.write(self.style.ERROR(error))
            raise CommandError(f"{len(resultado.errores)} errores: no se ha importado nada")
        if dry_run:
            self.stdout.write(self.style.NOTICE("Dry run: no se ha guardado nada"))
        self.stdout.write(
            self.style.SUCCESS(
                f"Creados: {resultado.creados} · Ya existían: {resultado.existentes}"
            )
        )
