"""Tareas automáticas del sistema. Corre en su propio contenedor (`tareas` en docker-compose.yml).

Apenas pasan las 00:00 cierra los turnos que quedaron abiertos y genera el cierre del día,
sin que nadie tenga que pedirlo.
"""

import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from turnos import servicios

SEGUNDOS_ENTRE_REVISIONES = 20


class Command(BaseCommand):
    help = "Cierra automáticamente cada día a las 00:00 (turnos abiertos y cierre del día)."

    def handle(self, *args, **opciones):
        self.stdout.write("Planificador iniciado: revisa cada 20 segundos si terminó el día.")
        while True:
            try:
                close_old_connections()
                for cierre in servicios.cerrar_dias_pendientes():
                    self.stdout.write(f"Cierre automático del día {cierre.fecha:%d/%m/%Y} generado.")
            except Exception as e:  # la base puede no estar lista todavía: se reintenta
                self.stderr.write(f"No se pudo revisar el cierre del día: {e}")
            time.sleep(SEGUNDOS_ENTRE_REVISIONES)
