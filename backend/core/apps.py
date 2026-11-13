from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Funciones generales del sistema (estado de la API, utilidades)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
