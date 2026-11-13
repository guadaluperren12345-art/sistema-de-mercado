from django.contrib import admin

from .models import Gasto


@admin.register(Gasto)
class GastoAdmin(admin.ModelAdmin):
    """Solo consulta (RNF-07): los gastos se anotan y se anulan desde el sistema, para que quede registrado."""

    list_display = ["id", "fecha_hora", "monto", "proposito", "usuario", "anulado"]
    list_filter = ["anulado"]
    search_fields = ["proposito"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
