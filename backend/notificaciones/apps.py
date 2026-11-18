from django.apps import AppConfig


class NotificacionesConfig(AppConfig):
    """Avisos a los dueños: la caja del día por Telegram, por correo y dentro del sistema."""

    default_auto_field = "django.db.models.AutoField"
    name = "notificaciones"
    verbose_name = "Notificaciones"
