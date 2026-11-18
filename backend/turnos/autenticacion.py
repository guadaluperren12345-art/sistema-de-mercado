"""Autenticación de la API: token JWT + turno abierto.

Un empleado o encargado solo puede usar el sistema mientras su turno está abierto.
Cuando el turno se cierra (cerró su cuenta en otro dispositivo, o lo cerró un dueño),
su sesión deja de servir y tiene que volver a ingresar con su contraseña.

El sistema ya no corta las cuentas a ninguna hora: quien sigue trabajando pasada la medianoche
sigue con su misma cuenta hasta que la cierra. Solo se corta la que quedó olvidada de un día anterior.
"""

from datetime import timedelta

from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from . import servicios
from .models import Turno

MENSAJE_TURNO_CERRADO = "Tu turno terminó. Volvé a iniciar sesión."


class AutenticacionConTurno(JWTAuthentication):
    def authenticate(self, request):
        resultado = super().authenticate(request)
        if resultado is None:
            return None
        usuario, token = resultado
        usuario.turno_abierto = None  # los dueños no llevan turno

        if servicios.lleva_turno(usuario):
            ahora = timezone.now()
            if servicios.cerrar_turno_olvidado(usuario, ahora):
                turno = None  # era una cuenta olvidada de un día anterior: tiene que volver a entrar
            else:
                turno = Turno.objects.filter(usuario_id=usuario.pk, fin__isnull=True).first()
            if turno is None:
                raise AuthenticationFailed(MENSAJE_TURNO_CERRADO, code="turno_cerrado")
            # Se anota la última actividad (como mucho una vez por minuto, para no escribir de más)
            if ahora - turno.ultima_actividad > timedelta(minutes=1):
                Turno.objects.filter(pk=turno.pk).update(ultima_actividad=ahora)
            usuario.turno_abierto = turno

        return usuario, token
