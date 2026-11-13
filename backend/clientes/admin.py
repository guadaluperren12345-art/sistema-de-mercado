from django.contrib import admin

from .models import CambioCliente, Cliente, MovimientoCuenta


class SoloConsulta(admin.ModelAdmin):
    """Solo consulta (RNF-07): todo se hace desde el sistema, para que quede registrado quién lo hizo."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Cliente)
class ClienteAdmin(SoloConsulta):
    list_display = ["nombre", "dni", "telefono", "saldo", "limite", "activo"]
    list_filter = ["activo"]
    search_fields = ["nombre", "dni"]


@admin.register(MovimientoCuenta)
class MovimientoCuentaAdmin(SoloConsulta):
    list_display = ["id", "fecha_hora", "cliente", "tipo", "importe", "saldo_resultante", "medio_pago", "usuario"]
    list_filter = ["tipo", "medio_pago"]


@admin.register(CambioCliente)
class CambioClienteAdmin(SoloConsulta):
    list_display = ["fecha_hora", "accion", "cliente", "realizado_por", "detalle"]
    list_filter = ["accion"]
