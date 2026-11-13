"""Modelos del módulo de acceso (documentación, sección 7.1)."""

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class Rol(models.Model):
    """Rol de un usuario: Administrador, Encargado o Empleado (RF-15)."""

    ADMINISTRADOR = "Administrador"
    ENCARGADO = "Encargado"
    EMPLEADO = "Empleado"

    nombre = models.CharField(max_length=30, unique=True)
    descripcion = models.CharField(max_length=200, blank=True, null=True)

    class Meta:
        db_table = "rol"
        verbose_name = "rol"
        verbose_name_plural = "roles"

    def __str__(self):
        return self.nombre


class UsuarioManager(BaseUserManager):
    def create_user(self, nombre_usuario, password=None, **campos):
        if not nombre_usuario:
            raise ValueError("El nombre de usuario es obligatorio")
        if "rol" not in campos and "rol_id" not in campos:
            campos["rol"] = Rol.objects.get(nombre=Rol.EMPLEADO)
        usuario = self.model(nombre_usuario=nombre_usuario, **campos)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_superuser(self, nombre_usuario, password=None, **campos):
        """Usado por `manage.py createsuperuser`: crea un dueño (administrador)."""
        campos["rol"] = Rol.objects.get(nombre=Rol.ADMINISTRADOR)
        campos.setdefault("is_superuser", True)
        campos.setdefault("debe_cambiar_password", False)
        return self.create_user(nombre_usuario, password, **campos)


class Usuario(AbstractBaseUser, PermissionsMixin):
    """Persona que usa el sistema, con su propia cuenta y contraseña."""

    MAX_INTENTOS = 5  # RF-07
    MINUTOS_BLOQUEO = 15

    nombre_usuario = models.CharField("nombre de usuario", max_length=50, unique=True)
    nombre = models.CharField(max_length=50)
    apellido = models.CharField(max_length=50)
    dni = models.CharField("DNI", max_length=10, unique=True)  # RN-02
    email = models.EmailField(max_length=100, blank=True, null=True)
    rol = models.ForeignKey(Rol, on_delete=models.PROTECT, related_name="usuarios")
    activo = models.BooleanField(default=True)
    debe_cambiar_password = models.BooleanField(default=True)  # RF-14
    # Un dueño puede autorizar a un encargado a dar de alta y corregir clientes de cuenta corriente (RF-96)
    puede_gestionar_clientes = models.BooleanField(default=False)
    intentos_fallidos = models.IntegerField(default=0)
    bloqueado_hasta = models.DateTimeField(blank=True, null=True)
    fecha_creacion = models.DateTimeField(default=timezone.now)
    creado_por = models.ForeignKey(
        "self", on_delete=models.SET_NULL, blank=True, null=True, related_name="usuarios_creados"
    )

    # Django lo llama last_login; en la base se guarda como "ultimo_acceso"
    last_login = models.DateTimeField("último acceso", blank=True, null=True, db_column="ultimo_acceso")

    objects = UsuarioManager()

    USERNAME_FIELD = "nombre_usuario"
    REQUIRED_FIELDS = ["nombre", "apellido", "dni"]

    class Meta:
        db_table = "usuario"
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def __str__(self):
        return f"{self.nombre} {self.apellido} ({self.nombre_usuario})"

    def save(self, *args, **kwargs):
        # Los dueños tienen todos los permisos, también en el panel /admin/,
        # sin importar cómo se creó la cuenta (createsuperuser, panel o API).
        self.is_superuser = self.rol.nombre == Rol.ADMINISTRADOR
        campos = kwargs.get("update_fields")
        if campos is not None and "rol" in campos:
            kwargs["update_fields"] = [*campos, "is_superuser"]
        super().save(*args, **kwargs)

    # --- Propiedades que Django necesita ---
    @property
    def is_active(self):
        return self.activo

    @property
    def is_staff(self):
        """Solo los administradores pueden entrar al panel de Django."""
        return self.es_administrador

    # --- Ayudas para los permisos por rol ---
    @property
    def es_administrador(self):
        return self.rol.nombre == Rol.ADMINISTRADOR

    @property
    def es_encargado(self):
        return self.rol.nombre == Rol.ENCARGADO

    @property
    def gestiona_clientes(self):
        """Los dueños siempre; un encargado, solo si un dueño lo autorizó."""
        return self.es_administrador or (self.es_encargado and self.puede_gestionar_clientes)

    @property
    def nombre_completo(self):
        return f"{self.nombre} {self.apellido}"

    # --- Bloqueo por intentos fallidos (RF-07) ---
    @property
    def esta_bloqueado(self):
        return self.bloqueado_hasta is not None and self.bloqueado_hasta > timezone.now()

    def registrar_intento_fallido(self):
        self.intentos_fallidos += 1
        if self.intentos_fallidos >= self.MAX_INTENTOS:
            self.bloqueado_hasta = timezone.now() + timezone.timedelta(minutes=self.MINUTOS_BLOQUEO)
            self.intentos_fallidos = 0
        self.save(update_fields=["intentos_fallidos", "bloqueado_hasta"])

    def registrar_ingreso_exitoso(self):
        self.intentos_fallidos = 0
        self.bloqueado_hasta = None
        self.last_login = timezone.now()
        self.save(update_fields=["intentos_fallidos", "bloqueado_hasta", "last_login"])

    def desbloquear(self):
        self.intentos_fallidos = 0
        self.bloqueado_hasta = None
        self.save(update_fields=["intentos_fallidos", "bloqueado_hasta"])


class CambioUsuario(models.Model):
    """Historial de cambios sobre las cuentas: quién dio de alta o de baja a quién (RF-19).

    Es de solo lectura (RNF-07): no se modifica ni se borra desde el sistema.
    """

    ALTA = "ALTA"
    BAJA = "BAJA"
    REACTIVACION = "REACTIVACION"
    PERMISO = "PERMISO"
    ACCIONES = [
        (ALTA, "Alta de usuario"),
        (BAJA, "Baja de usuario"),
        (REACTIVACION, "Reactivación de usuario"),
        (PERMISO, "Cambio de permiso"),
    ]

    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name="cambios_recibidos")
    realizado_por = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name="cambios_realizados")
    accion = models.CharField(max_length=20, choices=ACCIONES)
    detalle = models.CharField(max_length=300, blank=True, null=True)
    fecha_hora = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "cambio_usuario"
        verbose_name = "cambio de usuario"
        verbose_name_plural = "cambios de usuarios"
        ordering = ["-fecha_hora"]

    def __str__(self):
        return f"{self.fecha_hora:%d/%m/%Y %H:%M} {self.accion} {self.usuario_id} por {self.realizado_por_id}"


class TokenInvalidado(models.Model):
    """Tokens de renovación que ya no sirven: por cierre de sesión o porque se renovaron.

    Cada token tiene un identificador único (jti). Si está en esta tabla, se rechaza.
    """

    jti = models.CharField(max_length=255, unique=True)
    vence = models.DateTimeField()  # luego de esta fecha se puede borrar (el token ya venció solo)
    fecha_hora = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "token_invalidado"
        verbose_name = "token invalidado"
        verbose_name_plural = "tokens invalidados"

    @classmethod
    def invalidar(cls, token):
        from datetime import datetime, timezone as dt_tz

        vence = datetime.fromtimestamp(token["exp"], tz=dt_tz.utc)
        cls.objects.get_or_create(jti=token["jti"], defaults={"vence": vence})

    @classmethod
    def esta_invalidado(cls, token):
        return cls.objects.filter(jti=token["jti"]).exists()


class RegistroAcceso(models.Model):
    """Historial de accesos: logins, logouts, bloqueos y cambios de contraseña (RF-18)."""

    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    BLOQUEO = "BLOQUEO"
    CAMBIO_PASSWORD = "CAMBIO_PASSWORD"
    TIPOS = [
        (LOGIN, "Inicio de sesión"),
        (LOGOUT, "Cierre de sesión"),
        (BLOQUEO, "Bloqueo de cuenta"),
        (CAMBIO_PASSWORD, "Cambio de contraseña"),
    ]

    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, blank=True, null=True, related_name="accesos"
    )
    nombre_usuario_ingresado = models.CharField(max_length=50)
    tipo = models.CharField(max_length=20, choices=TIPOS)
    exitoso = models.BooleanField()
    ip = models.CharField(max_length=45, blank=True, null=True)
    dispositivo = models.CharField(max_length=200, blank=True, null=True)
    fecha_hora = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "registro_acceso"
        verbose_name = "registro de acceso"
        verbose_name_plural = "registros de acceso"
        ordering = ["-fecha_hora"]

    def __str__(self):
        estado = "OK" if self.exitoso else "FALLIDO"
        return f"{self.fecha_hora:%d/%m/%Y %H:%M} {self.tipo} {self.nombre_usuario_ingresado} {estado}"

    @classmethod
    def registrar(cls, request, tipo, exitoso, usuario=None, nombre_usuario=""):
        return cls.objects.create(
            usuario=usuario,
            nombre_usuario_ingresado=(nombre_usuario or getattr(usuario, "nombre_usuario", ""))[:50],
            tipo=tipo,
            exitoso=exitoso,
            ip=request.META.get("REMOTE_ADDR"),
            dispositivo=request.META.get("HTTP_USER_AGENT", "")[:200] or None,
        )
