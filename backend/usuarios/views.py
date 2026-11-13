"""API de acceso: login, logout, datos del usuario y cambio de contraseña."""

import math
from datetime import timedelta

import jwt
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken

from turnos import servicios
from turnos.models import Turno

from .models import RegistroAcceso, TokenInvalidado, Usuario
from .serializers import (
    CambiarPasswordSerializer,
    LoginSerializer,
    LogoutSerializer,
    UsuarioActualSerializer,
)

MENSAJE_GENERICO = "Usuario o contraseña incorrectos."  # RF-02


def respuesta_bloqueado(usuario):
    minutos = math.ceil((usuario.bloqueado_hasta - timezone.now()).total_seconds() / 60)
    return Response(
        {"detail": f"Cuenta bloqueada por demasiados intentos fallidos. Intente de nuevo en {minutos} minuto(s)."},
        status=status.HTTP_403_FORBIDDEN,
    )


class LoginView(APIView):
    """POST /api/auth/login/  {nombre_usuario, password}  (RF-01, RF-02, RF-07, RF-18)"""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        datos = LoginSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        nombre = datos.validated_data["nombre_usuario"].strip()
        password = datos.validated_data["password"]

        usuario = Usuario.objects.select_related("rol").filter(nombre_usuario=nombre).first()

        if usuario is None:
            make_password(password)  # tarda lo mismo que un usuario real: no revela si existe
            RegistroAcceso.registrar(request, RegistroAcceso.LOGIN, False, nombre_usuario=nombre)
            return Response({"detail": MENSAJE_GENERICO}, status=status.HTTP_401_UNAUTHORIZED)

        if usuario.esta_bloqueado:
            RegistroAcceso.registrar(request, RegistroAcceso.LOGIN, False, usuario)
            return respuesta_bloqueado(usuario)

        if not usuario.check_password(password):
            usuario.registrar_intento_fallido()
            RegistroAcceso.registrar(request, RegistroAcceso.LOGIN, False, usuario)
            if usuario.esta_bloqueado:
                RegistroAcceso.registrar(request, RegistroAcceso.BLOQUEO, True, usuario)
                return respuesta_bloqueado(usuario)
            return Response({"detail": MENSAJE_GENERICO}, status=status.HTTP_401_UNAUTHORIZED)

        if not usuario.activo:  # RN-05
            RegistroAcceso.registrar(request, RegistroAcceso.LOGIN, False, usuario)
            return Response({"detail": MENSAJE_GENERICO}, status=status.HTTP_401_UNAUTHORIZED)

        usuario.registrar_ingreso_exitoso()
        RegistroAcceso.registrar(request, RegistroAcceso.LOGIN, True, usuario)
        # RF-21: al entrar con su contraseña empieza a contar su horario.
        # Antes se cierran los días anteriores, por si la computadora estuvo apagada a las 00:00.
        servicios.cerrar_dias_pendientes()
        servicios.abrir_turno(usuario)
        refresh = RefreshToken.for_user(usuario)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "usuario": UsuarioActualSerializer(usuario).data,
            }
        )


def leer_refresh(crudo):
    """Datos de un token de renovación, aunque ya esté vencido (hasta un día). None si no es válido.

    Se verifica la firma, así que nadie puede inventar uno. Aceptar los vencidos hace falta para
    registrar la salida cuando la sesión se corta por inactividad: a esa altura el token ya venció.
    """
    try:
        datos = jwt.decode(crudo, api_settings.SIGNING_KEY, algorithms=[api_settings.ALGORITHM],
                           options={"verify_exp": False})
    except jwt.PyJWTError:
        return None
    if datos.get("token_type") != "refresh" or "jti" not in datos or "exp" not in datos:
        return None
    if datos["exp"] < (timezone.now() - timedelta(days=1)).timestamp():
        return None
    return datos


class LogoutView(APIView):
    """POST /api/auth/logout/  {refresh, motivo?}  — invalida el token y termina el turno (RF-05, RF-23).

    La persona se identifica con su token de renovación. `motivo: "inactividad"` cuando la
    pantalla cerró la sesión sola por falta de uso (RF-06).
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        datos = LogoutSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        token = leer_refresh(datos.validated_data["refresh"])
        usuario = token and Usuario.objects.select_related("rol").filter(pk=token.get(api_settings.USER_ID_CLAIM)).first()
        if not usuario:
            return Response({"detail": "La sesión no es válida."}, status=status.HTTP_401_UNAUTHORIZED)
        if TokenInvalidado.esta_invalidado(token):
            return Response(status=status.HTTP_204_NO_CONTENT)  # esa sesión ya estaba cerrada

        TokenInvalidado.invalidar(token)
        por_inactividad = datos.validated_data.get("motivo") == "inactividad"
        servicios.cerrar_turno(usuario, Turno.INACTIVIDAD if por_inactividad else Turno.USUARIO)
        RegistroAcceso.registrar(request, RegistroAcceso.LOGOUT, True, usuario)
        return Response(status=status.HTTP_204_NO_CONTENT)


class UsuarioActualView(APIView):
    """GET /api/auth/yo/ — datos del usuario conectado (RF-04)."""

    permitir_password_pendiente = True

    def get(self, request):
        return Response(UsuarioActualSerializer(request.user).data)


class CambiarPasswordView(APIView):
    """POST /api/auth/cambiar-password/  {password_actual, password_nueva}  (RF-13, RF-14)"""

    permitir_password_pendiente = True

    def post(self, request):
        datos = CambiarPasswordSerializer(data=request.data, context={"request": request})
        datos.is_valid(raise_exception=True)
        usuario = request.user
        usuario.set_password(datos.validated_data["password_nueva"])
        usuario.debe_cambiar_password = False
        usuario.save(update_fields=["password", "debe_cambiar_password"])
        RegistroAcceso.registrar(request, RegistroAcceso.CAMBIO_PASSWORD, True, usuario)
        return Response(UsuarioActualSerializer(usuario).data)
