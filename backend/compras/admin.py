from django.contrib import admin

from .models import Comerciante, Compra, PagoCompra


class SoloConsulta(admin.ModelAdmin):
    """Solo consulta (RNF-07): todo se anota desde el sistema, para que quede registrado quién lo hizo."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Comerciante)
class ComercianteAdmin(SoloConsulta):
    list_display = ["nombre", "fecha_creacion"]
    search_fields = ["nombre"]


@admin.register(Compra)
class CompraAdmin(SoloConsulta):
    list_display = ["id", "fecha_hora", "comerciante", "nombre_producto", "cantidad", "costo_total", "pagado", "anulada"]
    list_filter = ["anulada", "comerciante"]


@admin.register(PagoCompra)
class PagoCompraAdmin(SoloConsulta):
    list_display = ["id", "fecha_hora", "compra", "importe", "medio_pago", "usuario"]
