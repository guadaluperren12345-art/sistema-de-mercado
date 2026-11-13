from rest_framework.routers import SimpleRouter

from .api import ComprasViewSet

router = SimpleRouter()
router.register("compras", ComprasViewSet, basename="compras")

urlpatterns = router.urls
