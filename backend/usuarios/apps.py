from django.apps import AppConfig


class UsuariosConfig(AppConfig):
    """Módulo de acceso: usuarios, roles, login y registro de accesos."""

    default_auto_field = "django.db.models.AutoField"
    name = "usuarios"
    verbose_name = "Usuarios y accesos"
