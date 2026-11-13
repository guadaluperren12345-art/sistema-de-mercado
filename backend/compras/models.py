"""Compras a comerciantes (etapa 7, RF-112 a RF-119): qué se le compró a quién, cuánto costó y si ya se pagó."""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class Comerciante(models.Model):
    """Proveedor al que los dueños le compran la mercadería. Se crea solo al anotar la primera compra."""

    nombre = models.CharField(max_length=100, unique=True)
    fecha_creacion = models.DateTimeField(default=timezone.now)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="comerciantes_creados"
    )

    class Meta:
        db_table = "comerciante"
        verbose_name = "comerciante"
        verbose_name_plural = "comerciantes"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Compra(models.Model):
    """Un renglón de la lista de compras: un producto comprado a un comerciante.

    No se borra nunca: un error se corrige anulándola (queda quién y por qué).
    """

    PAGADO = "PAGADO"    # verde: está todo pagado
    PARCIAL = "PARCIAL"  # amarillo: se pagó una parte, falta el resto
    DEBE = "DEBE"        # rojo: todavía no se pagó nada
    ESTADOS = {PAGADO: "Pagado", PARCIAL: "Falta pagar una parte", DEBE: "Sin pagar"}

    id = models.BigAutoField(primary_key=True)
    comerciante = models.ForeignKey(Comerciante, on_delete=models.PROTECT, related_name="compras")
    producto = models.ForeignKey("productos.Producto", on_delete=models.PROTECT, related_name="compras")
    # Nombre y unidad como eran al comprar, por si después se corrige el producto
    nombre_producto = models.CharField(max_length=100)
    unidad = models.CharField(max_length=10)
    # Total en unidades o kilos (es lo que suma al stock). Si se compró por caja, cajón…, lo calcula el sistema
    cantidad = models.DecimalField(max_digits=12, decimal_places=3)
    # En qué se compró: SUELTO (por unidad o kilo), CAJA, CAJON, BANDEJA, BOLSA, PACK o BULTO (RF-120)
    presentacion = models.CharField(max_length=10, default="SUELTO")
    # Cuántas cajas o cajones se compraron y cuánto trae cada uno (vacíos si se compró suelto)
    bultos = models.DecimalField(max_digits=10, decimal_places=3, blank=True, null=True)
    contenido = models.DecimalField(max_digits=12, decimal_places=3, blank=True, null=True)
    # Lo que costó toda esa cantidad, y cuánto sale cada unidad o kilo
    costo_total = models.DecimalField(max_digits=14, decimal_places=2)
    costo_unitario = models.DecimalField(max_digits=14, decimal_places=2)
    # Lo que ya se le pagó al comerciante por esta compra. Solo cambia con un PagoCompra.
    pagado = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    # Si al anotarla se sumó la mercadería al stock
    sumo_stock = models.BooleanField(default=True)
    nota = models.CharField(max_length=200, blank=True, null=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="compras")
    turno = models.ForeignKey("turnos.Turno", on_delete=models.PROTECT, blank=True, null=True, related_name="compras")
    # La pone el sistema: fecha y hora en que se anotó
    fecha_hora = models.DateTimeField(default=timezone.now)

    anulada = models.BooleanField(default=False)
    anulada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, blank=True, null=True, related_name="compras_anuladas"
    )
    anulada_en = models.DateTimeField(blank=True, null=True)
    motivo_anulacion = models.CharField(max_length=200, blank=True, null=True)

    class Meta:
        db_table = "compra"
        verbose_name = "compra a comerciante"
        verbose_name_plural = "compras a comerciantes"
        ordering = ["-fecha_hora", "-id"]

    def __str__(self):
        return f"Compra {self.numero} {self.nombre_producto} a {self.comerciante_id}"

    @property
    def numero(self):
        return f"{self.id:06d}"

    @property
    def por_bulto(self):
        """True si se compró por caja, cajón, bandeja… y no suelto."""
        return self.presentacion != "SUELTO" and bool(self.bultos)

    @property
    def presentacion_texto(self):
        """«2 cajones × 18 kg» si se compró por cajón; None si se compró suelto."""
        if not self.por_bulto:
            return None
        from productos.models import Producto

        def numero(valor):
            return f"{valor.normalize():f}".replace(".", ",")

        nombre = (dict(Producto.PRESENTACIONES)[self.presentacion].lower() if self.bultos == 1
                  else Producto.PLURALES[self.presentacion])
        return f"{numero(self.bultos)} {nombre} × {numero(self.contenido)} {'kg' if self.unidad == 'KG' else 'u.'}"

    @property
    def costo_bulto(self):
        """Lo que salió cada caja o cajón. None si se compró suelto."""
        if not self.por_bulto:
            return None
        return (self.costo_total / self.bultos).quantize(Decimal("0.01"))

    @property
    def falta(self):
        """Lo que todavía hay que pagarle al comerciante por esta compra."""
        return max(self.costo_total - self.pagado, Decimal(0))

    @property
    def estado(self):
        if self.pagado >= self.costo_total:
            return self.PAGADO
        return self.PARCIAL if self.pagado > 0 else self.DEBE


class PagoCompra(models.Model):
    """Plata que se le pagó a un comerciante por una compra. Solo lectura (RNF-07)."""

    id = models.BigAutoField(primary_key=True)
    compra = models.ForeignKey(Compra, on_delete=models.PROTECT, related_name="pagos")
    importe = models.DecimalField(max_digits=14, decimal_places=2)
    medio_pago = models.CharField(max_length=15)  # EFECTIVO, DEBITO, CREDITO, TRANSFERENCIA o QR
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="pagos_compras")
    turno = models.ForeignKey(
        "turnos.Turno", on_delete=models.PROTECT, blank=True, null=True, related_name="pagos_compras"
    )
    fecha_hora = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "pago_compra"
        verbose_name = "pago a comerciante"
        verbose_name_plural = "pagos a comerciantes"
        ordering = ["fecha_hora", "id"]

    def __str__(self):
        return f"{self.fecha_hora:%d/%m/%Y %H:%M} ${self.importe} compra {self.compra_id}"
