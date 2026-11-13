from rest_framework.routers import SimpleRouter

from .api import CategoriasViewSet, MovimientosViewSet, PreciosViewSet, ProductosViewSet, SeccionesViewSet

router = SimpleRouter()
router.register("movimientos", MovimientosViewSet, basename="movimientos")
router.register("secciones", SeccionesViewSet, basename="secciones")
router.register("categorias", CategoriasViewSet, basename="categorias")
router.register("precios", PreciosViewSet, basename="precios")
router.register("productos",ProductosViewSet, basename="productos")

urlpatterns = router.urls
