"""Autenticación de la API: token JWT + turno abierto.

Un empleado o encargado solo puede usar el sistema mientras su turno está abierto.
Cuando el turno se cierra (cerró sesión en otro dispositivo, o el sistema lo cerró a las 00:00),
su sesión deja de servir y tiene que volver a ingresar con su contraseña.
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
            turno = Turno.objects.filter(usuario_id=usuario.pk, fin__isnull=True).first()
            if turno and turno.inicio < servicios.inicio_del_dia(servicios.fecha_local(ahora)):
                # Quedó abierto de un día anterior y el planificador todavía no pasó: se cierra ahora
                servicios.cerrar_dias_pendientes(ahora)
                turno = None
            if turno is None:
                raise AuthenticationFailed(MENSAJE_TURNO_CERRADO, code="turno_cerrado")
            # Se anota la última actividad (como mucho una vez por minuto, para no escribir de más)
            if ahora - turno.ultima_actividad > timedelta(minutes=1):
                Turno.objects.filter(pk=turno.pk).update(ultima_actividad=ahora)
            usuario.turno_abierto = turno

        return usuario, token
