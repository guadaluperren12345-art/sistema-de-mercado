from django.contrib import admin

from .models import CierreDiario, Turno


class SoloLectura(admin.ModelAdmin):
    """Los turnos se corrigen desde el sistema (queda registrado quién); acá solo se consultan (RNF-07)."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Turno)
class TurnoAdmin(SoloLectura):
    list_display = ["usuario", "inicio", "fin", "tipo_cierre", "para_revisar", "corregido_por"]
    list_filter = ["tipo_cierre", "para_revisar"]


@admin.register(CierreDiario)
class CierreDiarioAdmin(SoloLectura):
    list_display = ["fecha", "generado_en", "turnos", "minutos_trabajados", "valor_ingresado", "valor_perdidas"]
