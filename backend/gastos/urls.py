from rest_framework.routers import SimpleRouter

from .api import GastosViewSet

router = SimpleRouter()
router.register("gastos", GastosViewSet, basename="gastos")

urlpatterns = router.urls
