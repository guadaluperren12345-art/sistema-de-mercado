from django.apps import AppConfig


class GastosConfig(AppConfig):
    """Lista de gastos del día (etapa 8)."""

    default_auto_field = "django.db.models.AutoField"
    name = "gastos"
    verbose_name = "Gastos"
