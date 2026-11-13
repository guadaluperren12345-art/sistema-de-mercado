"""Secciones, categorías, productos y stock (documentación 4.6 y 7.2)."""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Seccion(models.Model):
    """División del mercado: Almacén, Carnicería o Verdulería (RF-29). Se cargan con una migración."""

    nombre = models.CharField(max_length=30, unique=True)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "seccion"
        verbose_name = "sección"
        verbose_name_plural = "secciones"
        ordering = ["orden"]

    def __str__(self):
        return self.nombre


class Categoria(models.Model):
    """Grupo de productos dentro de una sección (ej.: Carnicería → Pollo). Sirve para ajustar precios en conjunto."""

    seccion = models.ForeignKey(Seccion, on_delete=models.PROTECT, related_name="categorias")
    nombre = models.CharField(max_length=50)

    class Meta:
        db_table = "categoria"
        verbose_name = "categoría"
        verbose_name_plural = "categorías"
        ordering = ["seccion__orden", "nombre"]
        constraints = [
            models.UniqueConstraint(fields=["seccion", "nombre"], name="categoria_unica_por_seccion"),
        ]

    def __str__(self):
        return f"{self.seccion} → {self.nombre}"


class Producto(models.Model):
    """Producto que se vende en el mercado (RF-30 a RF-33)."""

    UNIDAD = "UNIDAD"
    KG = "KG"
    UNIDADES = [(UNIDAD, "Por unidad"), (KG, "Por kilo")]

    # Cómo llega la mercadería del comerciante. El stock y la venta siguen siendo por unidad o por kilo:
    # la presentación solo sirve para cargar más rápido lo que llega («3 cajones de 18 kg» = 54 kg).
    SUELTO = "SUELTO"
    PRESENTACIONES = [
        (SUELTO, "Suelto"),
        ("CAJA", "Caja"),
        ("CAJON", "Cajón"),
        ("BANDEJA", "Bandeja"),
        ("BOLSA", "Bolsa"),
        ("PACK", "Pack"),
        ("BULTO", "Bulto"),
    ]
    PLURALES = {"CAJA": "cajas", "CAJON": "cajones", "BANDEJA": "bandejas", "BOLSA": "bolsas",
                "PACK": "packs", "BULTO": "bultos"}

    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name="productos")
    nombre = models.CharField(max_length=100)
    # Número de producto: código corto propio (ej.: 101), cómodo para lo que se pesa o no trae código de barras
    codigo = models.CharField("número de producto", max_length=30, blank=True, null=True)
    # Código de barras del envase: es lo que escribe el lector al escanear
    codigo_barras = models.CharField("código de barras", max_length=30, blank=True, null=True)
    unidad = models.CharField(max_length=10, choices=UNIDADES, default=UNIDAD)
    # Precio por unidad o por kilo, según `unidad`. DECIMAL, nunca FLOAT (documentación 7.2)
    precio_venta = models.DecimalField(max_digits=14, decimal_places=2)
    precio_costo = models.DecimalField(max_digits=14, decimal_places=2)
    presentacion = models.CharField("llega en", max_length=10, choices=PRESENTACIONES, default=SUELTO)
    # Cuántas unidades o kilos trae cada caja, cajón, bandeja… (vacío si llega suelto)
    contenido = models.DecimalField(max_digits=12, decimal_places=3, blank=True, null=True)
    # Stock en unidades o en kilos, según `unidad`. Nadie lo escribe a mano (RN-09):
    # solo cambia con un MovimientoStock. Se guarda acá para que el semáforo sea rápido.
    stock_actual = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    stock_minimo = models.DecimalField("stock mínimo", max_digits=12, decimal_places=3, default=0)
    activo = models.BooleanField(default=True)  # RF-33: la baja no borra el producto
    fecha_creacion = models.DateTimeField(default=timezone.now)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="productos_creados"
    )

    class Meta:
        db_table = "producto"
        verbose_name = "producto"
        verbose_name_plural = "productos"
        ordering = ["nombre"]
        constraints = [
            # Único solo cuando tiene código (en SQL Server, UNIQUE común no admite dos NULL)
            models.UniqueConstraint(fields=["codigo"], condition=Q(codigo__isnull=False), name="producto_codigo_unico"),
            models.UniqueConstraint(
                fields=["codigo_barras"], condition=Q(codigo_barras__isnull=False), name="producto_codigo_barras_unico"
            ),
        ]

    def __str__(self):
        return self.nombre

    @property
    def seccion(self):
        return self.categoria.seccion

    @property
    def presentacion_texto(self):
        """«Cajón de 18 kg», «Pack de 6 u.» o «Suelto»."""
        if self.presentacion == self.SUELTO or not self.contenido:
            return "Suelto"
        numero = f"{self.contenido.normalize():f}".replace(".", ",")
        return f"{self.get_presentacion_display()} de {numero} {'kg' if self.unidad == self.KG else 'u.'}"

    @property
    def semaforo(self):
        """Color del stock (RF-38): ROJO sin stock, AMARILLO en el mínimo o menos, VERDE suficiente."""
        if self.stock_actual <= 0:
            return "ROJO"
        if self.stock_actual <= self.stock_minimo:
            return "AMARILLO"
        return "VERDE"


class MovimientoStock(models.Model):
    """Cada entrada o salida de mercadería (RF-35). Es la única forma de cambiar el stock (RN-09).

    Solo lectura (RNF-07): un error se corrige con otro movimiento, no borrando este.
    """

    INGRESO = "INGRESO"
    PERDIDA = "PERDIDA"
    AJUSTE = "AJUSTE"
    VENTA = "VENTA"  # lo va a usar el módulo de ventas (etapa 5)
    TIPOS = [
        (INGRESO, "Ingreso de mercadería"),
        (PERDIDA, "Pérdida"),
        (AJUSTE, "Ajuste por recuento"),
        (VENTA, "Venta"),
    ]

    id = models.BigAutoField(primary_key=True)
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name="movimientos")
    tipo = models.CharField(max_length=10, choices=TIPOS)
    # Con signo: positivo entra mercadería, negativo sale
    cantidad = models.DecimalField(max_digits=12, decimal_places=3)
    stock_resultante = models.DecimalField(max_digits=12, decimal_places=3)
    # Costo por unidad o kilo en ese momento: sirve para valorizar lo que entró o se perdió
    costo_unitario = models.DecimalField(max_digits=14, decimal_places=2)
    motivo = models.CharField(max_length=200, blank=True, null=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="movimientos_stock"
    )
    # Turno en el que se hizo (RF-24). NULL cuando lo hizo un dueño, que no lleva turno
    turno = models.ForeignKey(
        "turnos.Turno", on_delete=models.PROTECT, blank=True, null=True, related_name="movimientos_stock"
    )
    fecha_hora = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "movimiento_stock"
        verbose_name = "movimiento de stock"
        verbose_name_plural = "movimientos de stock"
        ordering = ["-fecha_hora", "-id"]

    def __str__(self):
        return f"{self.fecha_hora:%d/%m/%Y %H:%M} {self.tipo} {self.producto_id} {self.cantidad}"

    @property
    def valor(self):
        """Valor del movimiento al costo, con el mismo signo que la cantidad."""
        return (self.cantidad * self.costo_unitario).quantize(Decimal("0.01"))


class CambioProducto(models.Model):
    """Historial de altas, bajas, reactivaciones y correcciones de productos (auditoría). Solo lectura (RNF-07)."""

    ALTA = "ALTA"
    BAJA = "BAJA"
    REACTIVACION = "REACTIVACION"
    EDICION = "EDICION"
    PRECIO = "PRECIO"
    ACCIONES = [
        (ALTA, "Alta de producto"),
        (BAJA, "Baja de producto"),
        (REACTIVACION, "Reactivación de producto"),
        (EDICION, "Corrección de datos"),
        (PRECIO, "Cambio de precio"),
    ]

    id = models.BigAutoField(primary_key=True)
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name="cambios")
    realizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cambios_productos"
    )
    accion = models.CharField(max_length=20, choices=ACCIONES)
    detalle = models.CharField(max_length=300, blank=True, null=True)
    fecha_hora = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "cambio_producto"
        verbose_name = "cambio de producto"
        verbose_name_plural = "cambios de productos"
        ordering = ["-fecha_hora"]

    def __str__(self):
        return f"{self.fecha_hora:%d/%m/%Y %H:%M} {self.accion} {self.producto_id}"
