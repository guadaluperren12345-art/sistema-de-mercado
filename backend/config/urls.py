from django.contrib import admin
from django.urls import include, path

from core.views import estado

admin.site.site_header = "Sistema de Mercado"
admin.site.site_title = "Sistema de Mercado"
admin.site.index_title = "Administración"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/estado/", estado, name="estado"),
    path("api/auth/", include("usuarios.urls")),
    path("api/usuarios/", include("usuarios.urls_gestion")),
    path("api/", include("productos.urls")),  # secciones, categorías, productos y stock
    path("api/", include("ventas.urls")),  # ventas y recibos
    path("api/", include("clientes.urls")),  # clientes y cuenta corriente
    path("api/", include("gastos.urls")),  # lista de gastos
    path("api/", include("compras.urls")),  # compras a comerciantes
    path("api/", include("turnos.urls")),  # horarios, actividad, resumen y cierres del día
    path("api/", include("notificaciones.urls")),  # avisos a los dueños (caja del día)
]
