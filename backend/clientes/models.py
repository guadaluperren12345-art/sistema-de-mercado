"""Clientes y cuenta corriente («fiado») — etapa 9, RF-95 a RF-105."""

from django.conf import settings
from django.db import models
from django.utils import timezone


class ConfiguracionCuentas(models.Model):
    """Ajustes generales de las cuentas corrientes. Hay una sola fila (id = 1)."""

    # Tope de deuda para todos los clientes que no tienen uno propio. NULL = sin tope general
    limite_general = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)

    class Meta:
        db_table = "configuracion_cuentas"
        verbose_name = "configuración de cuentas corrientes"
        verbose_name_plural = "configuración de cuentas corrientes"

    def __str__(self):
        return "Configuración de cuentas corrientes"

    @classmethod
    def actual(cls):
        configuracion, _ = cls.objects.get_or_create(pk=1)
        return configuracion


class Cliente(models.Model):
    """Persona a la que se le vende fiado. Su deuda es `saldo`."""

    nombre = models.CharField(max_length=100, unique=True)
    dni = models.CharField("DNI o CUIT", max_length=13, blank=True, null=True)
    telefono = models.CharField("teléfono", max_length=30, blank=True, null=True)
    direccion = models.CharField("dirección", max_length=150, blank=True, null=True)
    nota = models.CharField(max_length=200, blank=True, null=True)
    # Tope de deuda propio de este cliente, puesto por un dueño. NULL = usa el tope general
    limite = models.DecimalField("límite propio", max_digits=14, decimal_places=2, blank=True, null=True)
    # Lo que debe. Nadie lo escribe a mano: solo cambia con un MovimientoCuenta.
    # Negativo = tiene plata a favor (por ejemplo, se anuló una compra que ya había pagado).
    saldo = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    activo = models.BooleanField(default=True)  # la baja no borra al cliente ni su deuda
    fecha_creacion = models.DateTimeField(default=timezone.now)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="clientes_creados"
    )

    class Meta:
        db_table = "cliente"
        verbose_name = "cliente"
        verbose_name_plural = "clientes"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class MovimientoCuenta(models.Model):
    """Cada cosa que cambia la deuda de un cliente. Solo lectura (RNF-07): un error se corrige con otro movimiento."""

    COMPRA = "COMPRA"
    PAGO = "PAGO"
    ANULACION = "ANULACION"
    AJUSTE = "AJUSTE"
    TIPOS = [
        (COMPRA, "Compra fiada"),
        (PAGO, "Pago"),
        (ANULACION, "Compra anulada o modificada"),
        (AJUSTE, "Ajuste de la cuenta"),
    ]

    id = models.BigAutoField(primary_key=True)  # también es el número del comprobante de pago
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="movimientos")
    tipo = models.CharField(max_length=10, choices=TIPOS)
    # Con signo: positivo aumenta la deuda (compra), negativo la baja (pago)
    importe = models.DecimalField(max_digits=14, decimal_places=2)
    saldo_resultante = models.DecimalField(max_digits=14, decimal_places=2)
    # La venta fiada, o la que se anuló
    venta = models.ForeignKey(
        "ventas.Venta", on_delete=models.PROTECT, blank=True, null=True, related_name="movimientos_cuenta"
    )
    # Con qué pagó (solo en los pagos): EFECTIVO, DEBITO, CREDITO, TRANSFERENCIA o QR
    medio_pago = models.CharField(max_length=15, blank=True, null=True)
    detalle = models.CharField(max_length=200, blank=True, null=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="movimientos_cuenta"
    )
    turno = models.ForeignKey(
        "turnos.Turno", on_delete=models.PROTECT, blank=True, null=True, related_name="movimientos_cuenta"
    )
    fecha_hora = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "movimiento_cuenta"
        verbose_name = "movimiento de cuenta corriente"
        verbose_name_plural = "movimientos de cuenta corriente"
        ordering = ["-fecha_hora", "-id"]

    def __str__(self):
        return f"{self.fecha_hora:%d/%m/%Y %H:%M} {self.tipo} {self.cliente_id} {self.importe}"

    @property
    def numero(self):
        return f"{self.id:06d}"


class CambioCliente(models.Model):
    """Historial de altas, bajas, correcciones y cambios de límite (auditoría). Solo lectura (RNF-07)."""

    ALTA = "ALTA"
    BAJA = "BAJA"
    REACTIVACION = "REACTIVACION"
    EDICION = "EDICION"
    LIMITE = "LIMITE"
    LIMITE_GENERAL = "LIMITE_GENERAL"
    ACCIONES = [
        (ALTA, "Alta de cliente"),
        (BAJA, "Baja de cliente"),
        (REACTIVACION, "Reactivación de cliente"),
        (EDICION, "Corrección de datos de cliente"),
        (LIMITE, "Cambio de límite de un cliente"),
        (LIMITE_GENERAL, "Cambio del límite general de fiado"),
    ]

    id = models.BigAutoField(primary_key=True)
    # NULL cuando el cambio es del límite general
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, blank=True, null=True, related_name="cambios")
    realizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cambios_clientes"
    )
    accion = models.CharField(max_length=20, choices=ACCIONES)
    detalle = models.CharField(max_length=300, blank=True, null=True)
    fecha_hora = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "cambio_cliente"
        verbose_name = "cambio de cliente"
        verbose_name_plural = "cambios de clientes"
        ordering = ["-fecha_hora"]

    def __str__(self):
        return f"{self.fecha_hora:%d/%m/%Y %H:%M} {self.accion} {self.cliente_id}"
