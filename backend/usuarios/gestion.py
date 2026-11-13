"""Gestión de usuarios: alta, baja y reactivación (solo administradores).

RF-08  crear usuarios                RF-10  desactivar y reactivar (no se borran)
RF-12  lista con rol, estado y último acceso
RF-19  cada cambio queda registrado con el administrador que lo hizo
RN-01/RN-02  usuario y DNI únicos    RN-03  siempre al menos un administrador activo
RN-04  un administrador no puede darse de baja a sí mismo
"""

import re

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as ErrorDjango
from django.db import transaction
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.validators import UniqueValidator

from turnos import servicios
from turnos.models import Turno

from .models import CambioUsuario, Rol, Usuario
from .permisos import EsAdministrador, PasswordAlDia


class UsuarioListaSerializer(serializers.ModelSerializer):
    rol = serializers.CharField(source="rol.nombre")
    bloqueado = serializers.BooleanField(source="esta_bloqueado")
    ultimo_acceso = serializers.DateTimeField(source="last_login")
    creado_por = serializers.SerializerMethodField()

    class Meta:
        model = Usuario
        fields = [
            "id", "nombre_usuario", "nombre", "apellido", "nombre_completo", "dni", "email",
            "rol", "activo", "bloqueado", "ultimo_acceso", "fecha_creacion", "creado_por",
            "puede_gestionar_clientes",
        ]

    def get_creado_por(self, usuario):
        return usuario.creado_por.nombre_completo if usuario.creado_por else None


class UsuarioAltaSerializer(serializers.ModelSerializer):
    """Datos para dar de alta un usuario (RF-08)."""

    nombre_usuario = serializers.CharField(
        max_length=50,
        validators=[UniqueValidator(Usuario.objects.all(), message="Ya existe un usuario con ese nombre de usuario.")],
    )
    dni = serializers.CharField(
        max_length=10,
        validators=[UniqueValidator(Usuario.objects.all(), message="Ya existe un usuario con ese DNI.")],
    )
    rol = serializers.SlugRelatedField(
        slug_field="nombre", queryset=Rol.objects.all(),
        error_messages={"does_not_exist": "El rol debe ser Administrador, Encargado o Empleado."},
    )
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    class Meta:
        model = Usuario
        fields = ["nombre_usuario", "nombre", "apellido", "dni", "email", "rol", "password"]
        extra_kwargs = {"email": {"required": False, "allow_null": True, "allow_blank": True}}

    def to_internal_value(self, datos):
        # Normaliza antes de validar: "Jperez " -> "jperez", "30.111.222" -> "30111222"
        datos = datos.copy()
        if isinstance(datos.get("nombre_usuario"), str):
            datos["nombre_usuario"] = datos["nombre_usuario"].strip().lower()
        if isinstance(datos.get("dni"), str):
            datos["dni"] = re.sub(r"[.\s-]", "", datos["dni"])
        return super().to_internal_value(datos)

    def validate_nombre_usuario(self, valor):
        if not re.fullmatch(r"[a-z0-9._]{3,50}", valor):
            raise serializers.ValidationError(
                "Usá entre 3 y 50 caracteres: letras sin acentos, números, punto o guion bajo, sin espacios."
            )
        return valor

    def validate_dni(self, valor):
        if not re.fullmatch(r"\d{7,8}", valor):
            raise serializers.ValidationError("El DNI debe tener 7 u 8 números.")
        return valor

    def validate_nombre(self, valor):
        return valor.strip()

    def validate_apellido(self, valor):
        return valor.strip()

    def validate_email(self, valor):
        return valor or None

    def validate(self, datos):
        # RN-06: misma regla de contraseña que en el cambio de contraseña
        usuario_temporal = Usuario(**{k: v for k, v in datos.items() if k != "password"})
        try:
            validate_password(datos["password"], usuario_temporal)
        except ErrorDjango as error:
            raise serializers.ValidationError({"password": list(error.messages)})
        return datos

    def create(self, datos):
        password = datos.pop("password")
        return Usuario.objects.create_user(
            password=password,
            debe_cambiar_password=True,  # RF-14: la cambia en su primer ingreso
            creado_por=self.context["request"].user,
            **datos,
        )


class UsuariosViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                      viewsets.GenericViewSet):
    """
    GET  /api/usuarios/                  lista (filtro opcional ?activo=1 o ?activo=0)
    POST /api/usuarios/                  alta
    GET  /api/usuarios/{id}/             datos de un usuario
    POST /api/usuarios/{id}/desactivar/  baja   {motivo?}
    POST /api/usuarios/{id}/reactivar/   reactivación
    POST /api/usuarios/{id}/permiso-clientes/  {permitir: true|false} — autoriza a un encargado a cargar clientes
    """

    # Al definir permission_classes se reemplazan los de settings: hay que repetir PasswordAlDia
    permission_classes = [EsAdministrador, PasswordAlDia]

    def get_queryset(self):
        qs = Usuario.objects.select_related("rol", "creado_por").order_by("apellido", "nombre")
        activo = self.request.query_params.get("activo")
        if activo in ("0", "1"):
            qs = qs.filter(activo=activo == "1")
        return qs

    def get_serializer_class(self):
        return UsuarioAltaSerializer if self.action == "create" else UsuarioListaSerializer

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        alta = UsuarioAltaSerializer(data=request.data, context={"request": request})
        alta.is_valid(raise_exception=True)
        usuario = alta.save()
        CambioUsuario.objects.create(
            usuario=usuario, realizado_por=request.user, accion=CambioUsuario.ALTA,
            detalle=f"Rol: {usuario.rol.nombre}",
        )
        return Response(UsuarioListaSerializer(usuario).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def desactivar(self, request, pk=None):
        usuario = self.get_object()
        if usuario.pk == request.user.pk:  # RN-04
            return error("No podés dar de baja tu propia cuenta.")
        if not usuario.activo:
            return error("Este usuario ya está dado de baja.")
        if usuario.es_administrador:  # RN-03
            otros_admins = Usuario.objects.filter(rol__nombre=Rol.ADMINISTRADOR, activo=True).exclude(pk=usuario.pk)
            if not otros_admins.exists():
                return error("Debe quedar al menos un dueño (administrador) activo.")

        usuario.activo = False
        usuario.save(update_fields=["activo"])
        # Si estaba trabajando, su turno termina en este momento (la sesión se le corta)
        servicios.cerrar_turno(usuario, Turno.ADMINISTRADOR)
        motivo = str(request.data.get("motivo", "")).strip()[:300] or None
        CambioUsuario.objects.create(
            usuario=usuario, realizado_por=request.user, accion=CambioUsuario.BAJA, detalle=motivo,
        )
        return Response(UsuarioListaSerializer(usuario).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def reactivar(self, request, pk=None):
        usuario = self.get_object()
        if usuario.activo:
            return error("Este usuario ya está activo.")
        usuario.activo = True
        usuario.save(update_fields=["activo"])
        CambioUsuario.objects.create(
            usuario=usuario, realizado_por=request.user, accion=CambioUsuario.REACTIVACION,
        )
        return Response(UsuarioListaSerializer(usuario).data)

    @action(detail=True, methods=["post"], url_path="permiso-clientes")
    @transaction.atomic
    def permiso_clientes(self, request, pk=None):
        """RF-96: el dueño decide qué encargados pueden dar de alta y corregir clientes de cuenta corriente."""
        usuario = self.get_object()
        if not usuario.es_encargado:
            return error("Este permiso es solo para encargados. Los dueños ya lo tienen y los empleados no pueden tenerlo.")
        permitir = request.data.get("permitir")
        if not isinstance(permitir, bool):
            return error("Indicá si se le da o se le quita el permiso.")
        if usuario.puede_gestionar_clientes != permitir:
            usuario.puede_gestionar_clientes = permitir
            usuario.save(update_fields=["puede_gestionar_clientes"])
            CambioUsuario.objects.create(
                usuario=usuario, realizado_por=request.user, accion=CambioUsuario.PERMISO,
                detalle="Puede cargar clientes de cuenta corriente" if permitir
                else "Ya no puede cargar clientes de cuenta corriente",
            )
        return Response(UsuarioListaSerializer(usuario).data)


def error(mensaje):
    return Response({"detail": mensaje}, status=status.HTTP_400_BAD_REQUEST)
