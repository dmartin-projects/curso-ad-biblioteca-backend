from django.core.management.base import BaseCommand

from prestamos.services import avisar_vencidos


class Command(BaseCommand):
    help = "Emite prestamo_vencido por cada préstamo fuera de plazo (en el módulo 26, una tarea de Beat)."

    def handle(self, *args, **options):
        n = avisar_vencidos()  # la lógica, en el servicio: el comando y la tarea solo lo llaman
        self.stdout.write(self.style.SUCCESS(f"{n} préstamos vencidos avisados"))
