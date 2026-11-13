"""Ventas y recibos (documentación 4.7 y 4.12)."""

from django.conf import settings
from django.db import models
from django.utils import timezone


class Venta(models.Model):
    """Una venta cobrada. Su recibo es esta misma venta impresa (no es una factura de ARCA).

    Las ventas no se borran nunca: un error se corrige anulándola (queda registrado quién y por qué).
    """

    EFECTIVO = "EFECTIVO"
    DEBITO = "DEBITO"
    CREDITO = "CREDITO"
    TRANSFERENCIA = "TRANSFERENCIA"
    QR = "QR"
    CUENTA = "CUENTA"  # fiado: no entra plata, se anota en la cuenta corriente del cliente
    MEDIOS = [
        (EFECTIVO, "Efectivo"),
        (DEBITO, "Tarjeta de débito"),
        (CREDITO, "Tarjeta de crédito"),
        (TRANSFERENCIA, "Transferencia"),
        (QR, "QR / billetera virtual"),
        (CUENTA, "Cuenta corriente (fiado)"),
    ]

    id = models.BigAutoField(primary_key=True)  # también es el número de recibo
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ventas")
    # Turno en el que se vendió (RF-39). NULL si vendió un dueño, que no lleva turno
    turno = models.ForeignKey("turnos.Turno", on_delete=models.PROTECT, blank=True, null=True, related_name="ventas")
    fecha_hora = models.DateTimeField(default=timezone.now)
    medio_pago = models.CharField(max_length=15, choices=MEDIOS)
    total = models.DecimalField(max_digits=14, decimal_places=2)
    # Solo en efectivo, si se cargó con cuánto pagó el cliente
    paga_con = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)
    vuelto = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)

    # A quién se le fió (solo cuando el medio de pago es cuenta corriente)
    cliente = models.ForeignKey(
        "clientes.Cliente", on_delete=models.PROTECT, blank=True, null=True, related_name="ventas"
    )

    # Buzón de recibos: los domingos el sistema saca los de más de una semana (la venta queda guardada)
    en_buzon = models.BooleanField(default=True)

    # Si esta venta es la versión corregida de otra (el cliente agregó o sacó algo después de pagar),
    # acá queda cuál era la original. La original no se borra: queda anulada como «reemplazada».
    corrige_a = models.ForeignKey(
        "self", on_delete=models.PROTECT, blank=True, null=True, related_name="correcciones"
    )

    anulada = models.BooleanField(default=False)
    anulada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, blank=True, null=True, related_name="ventas_anuladas"
    )
    anulada_en = models.DateTimeField(blank=True, null=True)
    motivo_anulacion = models.CharField(max_length=200, blank=True, null=True)

    class Meta:
        db_table = "venta"
        verbose_name = "venta"
        verbose_name_plural = "ventas"
        ordering = ["-fecha_hora", "-id"]

    def __str__(self):
        return f"Venta {self.numero} {self.fecha_hora:%d/%m/%Y %H:%M} ${self.total}"

    @property
    def numero(self):
        """Número de recibo con ceros adelante: 000123."""
        return f"{self.id:06d}"


class DetalleVenta(models.Model):
    """Un renglón de la venta. Guarda nombre, precio y costo del momento (RN-11):
    si después cambia el producto, el recibo y las ganancias pasadas no cambian."""

    id = models.BigAutoField(primary_key=True)
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name="detalles")
    producto = models.ForeignKey("productos.Producto", on_delete=models.PROTECT, related_name="ventas")
    nombre = models.CharField(max_length=100)
    unidad = models.CharField(max_length=10)
    cantidad = models.DecimalField(max_digits=12, decimal_places=3)
    precio_unitario = models.DecimalField(max_digits=14, decimal_places=2)
    costo_unitario = models.DecimalField(max_digits=14, decimal_places=2)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        db_table = "detalle_venta"
        verbose_name = "detalle de venta"
        verbose_name_plural = "detalles de venta"
        ordering = ["id"]

    def __str__(self):
        return f"{self.nombre} × {self.cantidad}"
