from rest_framework.routers import SimpleRouter

from .api import VentasViewSet

router = SimpleRouter()
router.register("ventas", VentasViewSet, basename="ventas")

urlpatterns = router.urls
