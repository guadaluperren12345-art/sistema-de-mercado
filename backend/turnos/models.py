"""Turnos (horario de trabajo) y cierre automático del día (documentación 4.5 y 4.11)."""

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Turno(models.Model):
    """Tiempo que un empleado o encargado tuvo su cuenta abierta: desde que entra hasta que cierra sesión.

    Los dueños (administradores) no llevan turno. Las horas trabajadas no se guardan:
    se calculan como fin − inicio.
    """

    USUARIO = "USUARIO"
    INACTIVIDAD = "INACTIVIDAD"
    SISTEMA = "SISTEMA"
    ADMINISTRADOR = "ADMINISTRADOR"
    TIPOS_CIERRE = [
        (USUARIO, "Cerró sesión"),
        (INACTIVIDAD, "Se cerró por inactividad"),
        (SISTEMA, "Quedó abierta: la cerró el sistema"),
        (ADMINISTRADOR, "Lo cerró un dueño"),
    ]

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="turnos")
    inicio = models.DateTimeField(default=timezone.now)
    fin = models.DateTimeField(blank=True, null=True)  # NULL = turno abierto
    # Último momento en que la persona usó el sistema. Ayuda al dueño a corregir un turno que quedó abierto.
    ultima_actividad = models.DateTimeField(default=timezone.now)
    tipo_cierre = models.CharField(max_length=20, choices=TIPOS_CIERRE, blank=True, null=True)
    # La persona se olvidó la cuenta abierta y el sistema la cerró: el dueño confirma o corrige la hora de salida
    para_revisar = models.BooleanField(default=False)

    # Corrección hecha por un dueño (queda registrado quién, cuándo y qué hora había antes)
    fin_original = models.DateTimeField(blank=True, null=True)
    corregido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, blank=True, null=True, related_name="turnos_corregidos"
    )
    corregido_en = models.DateTimeField(blank=True, null=True)
    nota = models.CharField(max_length=300, blank=True, null=True)

    class Meta:
        db_table = "turno"
        verbose_name = "turno"
        verbose_name_plural = "turnos"
        ordering = ["-inicio"]
        constraints = [
            # RN-07: un solo turno abierto por persona
            models.UniqueConstraint(fields=["usuario"], condition=Q(fin__isnull=True), name="un_turno_abierto_por_usuario"),
        ]

    def __str__(self):
        return f"{self.usuario_id} {self.inicio:%d/%m/%Y %H:%M}"

    @property
    def abierto(self):
        return self.fin is None

    @property
    def minutos(self):
        """Minutos trabajados. Si el turno sigue abierto, cuenta hasta este momento."""
        fin = self.fin or timezone.now()
        return max(0, int((fin - self.inicio).total_seconds() // 60))


class CierreDiario(models.Model):
    """Cierre automático del día (la caja): lo genera el sistema a las 00:45, sin que nadie lo pida.

    Guarda la foto de los totales del día del mercado (de 00:45 a 00:45). Solo lo ven los dueños,
    que además reciben un aviso con la caja hecha. Es de solo lectura (RNF-07).
    """

    fecha = models.DateField(unique=True)
    generado_en = models.DateTimeField(default=timezone.now)

    # Personal
    turnos = models.IntegerField(default=0)
    minutos_trabajados = models.IntegerField(default=0)
    turnos_cerrados_por_sistema = models.IntegerField(default=0)

    # Mercadería (valores al precio de costo)
    movimientos_stock = models.IntegerField(default=0)
    valor_ingresado = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    valor_perdidas = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    valor_ajustes = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    # Cantidad de cambios registrados ese día (productos, usuarios, stock y ventas)
    cambios = models.IntegerField(default=0)

    # Dinero de las ventas (sin las anuladas)
    ventas_cantidad = models.IntegerField(default=0)
    ventas_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    ventas_efectivo = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    # Cuenta corriente: lo que se vendió fiado (no entró plata) y lo que pagaron los clientes de su deuda
    ventas_fiado = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    cobros_cuenta = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    cobros_cuenta_efectivo = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    # Gastos anotados ese día (sin los anulados). Se guardan en positivo y se restan en la cuenta final
    gastos_cantidad = models.IntegerField(default=0)
    gastos_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    # Compras a comerciantes anotadas ese día y lo que se les pagó ese día (de cualquier compra)
    compras_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    pagos_comerciantes = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    pagos_comerciantes_efectivo = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    # Lo vendido menos lo que costó esa mercadería (todavía sin gastos)
    ganancia_bruta = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    @property
    def entro(self):
        """Plata que entró: lo vendido y cobrado en el momento, más los pagos de cuentas corrientes."""
        return self.ventas_total - self.ventas_fiado + self.cobros_cuenta

    @property
    def resultado_dia(self):
        """Cuenta final del día: lo que entró menos los gastos y menos lo pagado a comerciantes (RF-109, RF-118)."""
        return self.entro - self.gastos_total - self.pagos_comerciantes

    @property
    def efectivo_esperado(self):
        """Efectivo que debería haber: ventas y pagos en efectivo, menos los gastos (salen de la caja)."""
        return (self.ventas_efectivo + self.cobros_cuenta_efectivo - self.gastos_total
                - self.pagos_comerciantes_efectivo)

    class Meta:
        db_table = "cierre_diario"
        verbose_name = "cierre del día"
        verbose_name_plural = "cierres del día"
        ordering = ["-fecha"]

    def __str__(self):
        return f"Cierre {self.fecha:%d/%m/%Y}"
