"""Tareas automáticas del sistema. Corre en su propio contenedor (`tareas` en docker-compose.yml).

Apenas pasan las 00:45 hace la caja del día (el cierre) sin que nadie tenga que pedirlo, y les
avisa a los dueños. También manda los avisos que quedaron en cola (Telegram y correo) y los
reintenta si no había internet.
"""

import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from core.dia import TEXTO_HORA_DE_CIERRE
from notificaciones import servicios as avisos
from turnos import servicios

SEGUNDOS_ENTRE_REVISIONES = 20


class Command(BaseCommand):
    help = f"Hace la caja de cada día a las {TEXTO_HORA_DE_CIERRE} y manda los avisos a los dueños."

    def handle(self, *args, **opciones):
        self.stdout.write(f"Planificador iniciado: revisa cada 20 segundos si terminó el día ({TEXTO_HORA_DE_CIERRE}).")
        while True:
            try:
                close_old_connections()
                for cierre in servicios.cerrar_dias_pendientes():
                    self.stdout.write(f"Cierre automático del día {cierre.fecha:%d/%m/%Y} generado.")
            except Exception as e:  # la base puede no estar lista todavía: se reintenta
                self.stderr.write(f"No se pudo revisar el cierre del día: {e}")
            try:
                enviados = avisos.enviar_pendientes()
                if enviados:
                    self.stdout.write(f"Avisos enviados a los dueños: {enviados}.")
            except Exception as e:
                self.stderr.write(f"No se pudieron mandar los avisos: {e}")
            time.sleep(SEGUNDOS_ENTRE_REVISIONES)
