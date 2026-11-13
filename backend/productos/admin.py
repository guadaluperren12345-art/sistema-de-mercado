from django.contrib import admin

from .models import CambioProducto, Categoria, Producto, Seccion


@admin.register(Seccion)
class SeccionAdmin(admin.ModelAdmin):
    list_display = ["nombre", "orden"]


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ["nombre", "seccion"]
    list_filter = ["seccion"]


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ["nombre", "codigo", "categoria", "unidad", "precio_venta", "precio_costo", "activo"]
    list_filter = ["categoria__seccion", "activo", "unidad"]
    search_fields = ["nombre", "codigo"]
    # El stock no se edita a mano (RN-09): solo cambia con movimientos desde el sistema
    readonly_fields = ["fecha_creacion", "creado_por", "stock_actual"]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.creado_por = request.user
        super().save_model(request, obj, form, change)


@admin.register(CambioProducto)
class CambioProductoAdmin(admin.ModelAdmin):
    """Historial de solo lectura (RNF-07)."""

    list_display = ["fecha_hora", "accion", "producto", "realizado_por", "detalle"]
    list_filter = ["accion"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
