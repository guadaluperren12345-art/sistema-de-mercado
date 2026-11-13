"""Carga las 3 secciones del mercado (RF-29) y algunas categorías de ejemplo.

Las categorías se pueden agregar después desde el sistema.
"""

from django.db import migrations

SECCIONES = {
    "Almacén": ["Almacén general", "Bebidas", "Lácteos", "Limpieza", "Perfumería"],
    "Carnicería": ["Vacuno", "Pollo", "Cerdo", "Embutidos"],
    "Verdulería": ["Verduras", "Frutas"],
}


def cargar(apps, schema_editor):
    Seccion = apps.get_model("productos", "Seccion")
    Categoria = apps.get_model("productos", "Categoria")
    for orden, (nombre, categorias) in enumerate(SECCIONES.items(), start=1):
        seccion, _ = Seccion.objects.get_or_create(nombre=nombre, defaults={"orden": orden})
        for categoria in categorias:
            Categoria.objects.get_or_create(seccion=seccion, nombre=categoria)


def borrar(apps, schema_editor):
    Seccion = apps.get_model("productos", "Seccion")
    Categoria = apps.get_model("productos", "Categoria")
    Categoria.objects.filter(seccion__nombre__in=SECCIONES).delete()
    Seccion.objects.filter(nombre__in=SECCIONES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("productos", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(cargar, borrar),
    ]
