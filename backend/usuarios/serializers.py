from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .models import TokenInvalidado, Usuario


class RenovarTokenSerializer(TokenRefreshSerializer):
    """Renueva el token (RF-06) rechazando los invalidados y anulando el anterior."""

    def validate(self, attrs):
        anterior = RefreshToken(attrs["refresh"])  # valida firma y vencimiento
        if TokenInvalidado.esta_invalidado(anterior):
            raise InvalidToken("La sesión fue cerrada. Inicie sesión de nuevo.")
        # Empleados y encargados solo siguen conectados mientras su turno está abierto
        # (el sistema lo cierra a las 00:00).
        from turnos import servicios

        usuario = Usuario.objects.select_related("rol").filter(pk=anterior.get("user_id")).first()
        if usuario and servicios.lleva_turno(usuario) and servicios.turno_abierto(usuario) is None:
            raise InvalidToken("Tu turno terminó. Volvé a iniciar sesión.")
        datos = super().validate(attrs)  # también rechaza usuarios desactivados
        TokenInvalidado.invalidar(anterior)  # el token usado ya no sirve más
        return datos


class UsuarioActualSerializer(serializers.ModelSerializer):
    """Datos del usuario conectado que necesita el frontend (RF-04)."""

    rol = serializers.CharField(source="rol.nombre")
    nombre_completo = serializers.CharField()

    class Meta:
        model = Usuario
        fields = ["id", "nombre_usuario", "nombre", "apellido", "nombre_completo", "rol", "debe_cambiar_password",
                  "gestiona_clientes"]


class LoginSerializer(serializers.Serializer):
    nombre_usuario = serializers.CharField(max_length=50)
    password = serializers.CharField(max_length=128, trim_whitespace=False)


class CambiarPasswordSerializer(serializers.Serializer):
    password_actual = serializers.CharField(trim_whitespace=False)
    password_nueva = serializers.CharField(trim_whitespace=False)

    def validate(self, datos):
        usuario = self.context["request"].user
        if not usuario.check_password(datos["password_actual"]):
            raise serializers.ValidationError({"password_actual": "La contraseña actual no es correcta."})
        if datos["password_actual"] == datos["password_nueva"]:
            raise serializers.ValidationError({"password_nueva": "La nueva contraseña debe ser distinta de la actual."})
        validate_password(datos["password_nueva"], usuario)
        return datos


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()
    motivo = serializers.CharField(required=False, allow_blank=True, max_length=20)
