from django.urls import path
from rest_framework.routers import SimpleRouter

from .api import ClientesViewSet, ConfiguracionView

router = SimpleRouter()
router.register("clientes", ClientesViewSet, basename="clientes")

urlpatterns = [
    path("cuentas/configuracion/", ConfiguracionView.as_view(), name="cuentas_configuracion"),
    *router.urls,
]
