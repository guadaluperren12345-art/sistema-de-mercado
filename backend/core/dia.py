"""El «día del mercado».

El mercado sigue atendiendo pasada la medianoche, así que el día no termina a las 00:00 sino a
la HORA_DE_CIERRE (00:45): a esa hora el sistema hace solo la caja del día y les avisa a los dueños.
Una venta del sábado a las 00:20 todavía es del viernes.

Todo el sistema usa estas funciones para saber a qué día pertenece cada cosa. Si se cambia la
hora, cambiarla también en `frontend/src/formato.js` (HORA_CIERRE).
"""

from datetime import datetime, time, timedelta

from django.utils import timezone

HORA_DE_CIERRE = time(0, 45)
TEXTO_HORA_DE_CIERRE = HORA_DE_CIERRE.strftime("%H:%M")
_CORRIMIENTO = timedelta(hours=HORA_DE_CIERRE.hour, minutes=HORA_DE_CIERRE.minute)


def inicio_del_dia(fecha):
    """Momento en que empieza el día del mercado de esa fecha (las 00:45, hora de Argentina)."""
    return timezone.make_aware(datetime.combine(fecha, HORA_DE_CIERRE))


def fecha_local(momento):
    """A qué día del mercado pertenece un momento (antes de las 00:45 todavía es el día anterior)."""
    return (timezone.localtime(momento) - _CORRIMIENTO).date()


def hoy():
    """El día del mercado que está corriendo ahora."""
    return fecha_local(timezone.now())
