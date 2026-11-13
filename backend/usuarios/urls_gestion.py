from rest_framework.routers import SimpleRouter

from .gestion import UsuariosViewSet

router = SimpleRouter()
router.register("", UsuariosViewSet, basename="usuarios")

urlpatterns = router.urls
