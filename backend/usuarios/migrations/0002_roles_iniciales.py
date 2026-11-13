"""Carga los 3 roles del sistema (documentación 7.1, datos iniciales)."""

from django.db import migrations

ROLES = [
    ("Administrador", "Dueño del mercado, acceso total"),
    ("Encargado", "Empleado de confianza con permisos extra"),
    ("Empleado", "Personal del mercado, tareas diarias"),
]


def crear_roles(apps, schema_editor):
    Rol = apps.get_model("usuarios", "Rol")
    for nombre, descripcion in ROLES:
        Rol.objects.get_or_create(nombre=nombre, defaults={"descripcion": descripcion})


def borrar_roles(apps, schema_editor):
    Rol = apps.get_model("usuarios", "Rol")
    Rol.objects.filter(nombre__in=[n for n, _ in ROLES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("usuarios", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(crear_roles, borrar_roles),
    ]
