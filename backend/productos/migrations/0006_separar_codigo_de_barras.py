"""Hasta ahora había un solo campo «código» para el número de producto y para el código de barras.

Los códigos que son claramente de barras (solo números y 8 dígitos o más, como los EAN-8, UPC y EAN-13
de los envases) pasan al campo nuevo `codigo_barras`. Los cortos (ej.: 101) quedan como número de producto.
"""

from django.db import migrations


def separar(apps, schema_editor):
    Producto = apps.get_model("productos", "Producto")
    for p in Producto.objects.exclude(codigo__isnull=True):
        if p.codigo.isdigit() and len(p.codigo) >= 8:
            p.codigo_barras, p.codigo = p.codigo, None
            p.save(update_fields=["codigo", "codigo_barras"])


def volver(apps, schema_editor):
    Producto = apps.get_model("productos", "Producto")
    for p in Producto.objects.filter(codigo__isnull=True).exclude(codigo_barras__isnull=True):
        p.codigo = p.codigo_barras
        p.save(update_fields=["codigo"])


class Migration(migrations.Migration):

    dependencies = [
        ("productos", "0005_producto_codigo_barras_alter_producto_codigo_and_more"),
    ]

    operations = [migrations.RunPython(separar, volver)]
