from django.contrib import admin

from .models import DetalleVenta, Venta


class DetalleEnLinea(admin.TabularInline):
    model = DetalleVenta
    extra = 0
    can_delete = False


@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    """Solo consulta (RNF-07): las ventas se cobran y se anulan desde el sistema, para que quede registrado."""

    list_display = ["id", "fecha_hora", "usuario", "medio_pago", "total", "anulada", "en_buzon"]
    list_filter = ["medio_pago", "anulada", "en_buzon"]
    inlines = [DetalleEnLinea]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
