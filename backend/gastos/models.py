"""Gastos del mercado (etapa 8, RF-106 a RF-111): una lista donde cualquiera anota un monto y para qué fue."""

from django.conf import settings
from django.db import models
from django.utils import timezone


class Gasto(models.Model):
    """Plata que salió de la caja. No se borra nunca: un error se corrige anulándolo (queda quién y por qué)."""

    id = models.BigAutoField(primary_key=True)
    # Siempre en positivo. En las cuentas del día se resta.
    monto = models.DecimalField(max_digits=14, decimal_places=2)
    proposito = models.CharField("propósito", max_length=200)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="gastos")
    # Turno en el que se anotó. NULL si lo anotó un dueño, que no lleva turno
    turno = models.ForeignKey("turnos.Turno", on_delete=models.PROTECT, blank=True, null=True, related_name="gastos")
    fecha_hora = models.DateTimeField(default=timezone.now)

    anulado = models.BooleanField(default=False)
    anulado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, blank=True, null=True, related_name="gastos_anulados"
    )
    anulado_en = models.DateTimeField(blank=True, null=True)
    motivo_anulacion = models.CharField(max_length=200, blank=True, null=True)

    class Meta:
        db_table = "gasto"
        verbose_name = "gasto"
        verbose_name_plural = "gastos"
        ordering = ["-fecha_hora", "-id"]

    def __str__(self):
        return f"{self.fecha_hora:%d/%m/%Y %H:%M} -${self.monto} {self.proposito}"
