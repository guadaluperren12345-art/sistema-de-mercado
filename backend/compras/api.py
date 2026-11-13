"""API de compras a comerciantes. Todo es solo para dueños y encargados (RF-112).

Cada compra es un renglón: producto, cantidad, costo, comerciante, fecha y hora del sistema, y cuánto se pagó.
El color lo decide el pago: verde (pagado), amarillo (falta una parte) o rojo (sin pagar).
"""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from productos.api import (
    ProductoSerializer, inicio_del_dia, recordar_presentacion, registrar_movimiento, texto_cantidad,
)
from productos.models import CambioProducto, MovimientoStock, Producto
from usuarios.permisos import EsEncargadoOAdministrador, PasswordAlDia

from .models import Comerciante, Compra, PagoCompra

CENTAVOS = Decimal("0.01")
MAXIMO = 300
MEDIOS_DE_PAGO = [
    ("EFECTIVO", "Efectivo"),
    ("DEBITO", "Tarjeta de débito"),
    ("CREDITO", "Tarjeta de crédito"),
    ("TRANSFERENCIA", "Transferencia"),
    ("QR", "QR / billetera virtual"),
]
NOMBRE_MEDIO = dict(MEDIOS_DE_PAGO)


def error(mensaje, codigo=status.HTTP_400_BAD_REQUEST):
    return Response({"detail": str(mensaje)}, status=codigo)


# ---------- Serializers ----------

class PagoSerializer(serializers.ModelSerializer):
    medio_pago_texto = serializers.SerializerMethodField()
    usuario = serializers.CharField(source="usuario.nombre_completo")

    class Meta:
        model = PagoCompra
        fields = ["id", "importe", "medio_pago", "medio_pago_texto", "usuario", "fecha_hora"]

    def get_medio_pago_texto(self, pago):
        return NOMBRE_MEDIO.get(pago.medio_pago, pago.medio_pago)


class CompraSerializer(serializers.ModelSerializer):
    numero = serializers.CharField()
    comerciante_nombre = serializers.CharField(source="comerciante.nombre")
    seccion = serializers.CharField(source="producto.categoria.seccion.nombre")
    usuario = serializers.CharField(source="usuario.nombre_completo")
    falta = serializers.DecimalField(max_digits=14, decimal_places=2)
    estado = serializers.CharField()
    estado_texto = serializers.SerializerMethodField()
    anulada_por = serializers.SerializerMethodField()
    pagos = PagoSerializer(many=True)
    # Si se compró por caja, cajón…: «2 cajones × 18 kg» y lo que salió cada uno
    presentacion_texto = serializers.CharField()
    costo_bulto = serializers.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        model = Compra
        fields = [
            "id", "numero", "fecha_hora", "comerciante", "comerciante_nombre", "producto", "nombre_producto", "unidad",
            "seccion", "cantidad", "presentacion", "bultos", "contenido", "presentacion_texto", "costo_bulto",
            "costo_total", "costo_unitario", "pagado", "falta", "estado", "estado_texto",
            "sumo_stock", "nota", "usuario", "anulada", "anulada_por", "anulada_en", "motivo_anulacion", "pagos",
        ]

    def get_estado_texto(self, compra):
        return Compra.ESTADOS[compra.estado]

    def get_anulada_por(self, compra):
        return compra.anulada_por.nombre_completo if compra.anulada_por else None


class NuevaCompraSerializer(serializers.Serializer):
    # Nombre del comerciante: si no existe, se crea
    comerciante = serializers.CharField(
        max_length=100, error_messages={"blank": "Escribí a quién se le compró.", "required": "Escribí a quién se le compró."}
    )
    producto = serializers.PrimaryKeyRelatedField(
        queryset=Producto.objects.select_related("categoria__seccion"), required=False, allow_null=True,
        error_messages={"does_not_exist": "El producto no existe.", "incorrect_type": "Elegí el producto."},
    )
    # Si lo que se compró todavía no existe como producto, se crea en el momento y aparece en Productos
    # y en Stock (RF-122): {nombre, categoria, unidad, precio_venta}. El costo sale de esta compra.
    producto_nuevo = serializers.DictField(required=False, allow_null=True)
    # Se compra de una de dos formas (RF-120):
    # - suelto: `cantidad` en unidades o kilos;
    # - por caja, cajón, bandeja…: `presentacion`, `bultos` (cuántos) y `contenido` (cuánto trae cada uno;
    #   si falta se usa el que tiene cargado el producto). El sistema calcula la cantidad total.
    cantidad = serializers.DecimalField(
        max_digits=12, decimal_places=3, min_value=Decimal("0.001"), required=False, allow_null=True,
        error_messages={"min_value": "La cantidad tiene que ser mayor a 0.", "invalid": "Escribí la cantidad con números."},
    )
    presentacion = serializers.ChoiceField(
        choices=Producto.PRESENTACIONES, default=Producto.SUELTO,
        error_messages={"invalid_choice": "Elegí en qué se compró: suelto, caja, cajón, bandeja…"},
    )
    bultos = serializers.DecimalField(
        max_digits=10, decimal_places=3, required=False, allow_null=True,
        error_messages={"invalid": "Escribí cuántos se compraron, con números."},
    )
    contenido = serializers.DecimalField(
        max_digits=12, decimal_places=3, required=False, allow_null=True,
        error_messages={"invalid": "Escribí cuánto trae cada uno, con números."},
    )
    # Lo que costó toda esa cantidad
    costo_total = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=CENTAVOS,
        error_messages={"min_value": "El costo tiene que ser mayor a 0.", "required": "Escribí cuánto costó.",
                        "invalid": "Escribí el costo con números."},
    )
    # Lo que se paga ahora: todo (verde), una parte (amarillo) o nada (rojo)
    pagado = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0"), default=Decimal("0"),
        error_messages={"min_value": "Lo pagado no puede ser negativo.", "invalid": "Escribí lo pagado con números."},
    )
    medio_pago = serializers.ChoiceField(
        choices=MEDIOS_DE_PAGO, default="EFECTIVO", error_messages={"invalid_choice": "Elegí con qué se pagó."}
    )
    # Normalmente la compra suma al stock. Se desmarca si la mercadería ya se cargó en Stock.
    sumar_stock = serializers.BooleanField(default=True)
    nota = serializers.CharField(max_length=200, required=False, allow_blank=True)

    def validate_comerciante(self, valor):
        valor = " ".join(valor.split())
        if len(valor) < 2:
            raise serializers.ValidationError("Escribí a quién se le compró.")
        return valor[0].upper() + valor[1:]

    def validate(self, datos):
        nuevo = datos.get("producto_nuevo")
        p = datos.get("producto")
        if p is None and not nuevo:
            raise serializers.ValidationError({"producto": "Elegí el producto."})
        if p is None:
            # Todavía no existe: para las cuentas alcanza con saber si va por kilo o por unidad
            unidad = nuevo.get("unidad")
            if unidad not in (Producto.UNIDAD, Producto.KG):
                raise serializers.ValidationError({"producto_nuevo": {"unidad": ["Elegí si se vende por unidad o por kilo."]}})
            p = Producto(unidad=unidad, presentacion=Producto.SUELTO, activo=True)
        if not p.activo:
            raise serializers.ValidationError({"producto": "Ese producto está dado de baja. Reactivalo para comprarlo."})

        if datos["presentacion"] == Producto.SUELTO:
            datos["bultos"] = datos["contenido"] = None
            if datos.get("cantidad") is None:
                raise serializers.ValidationError({"cantidad": "Escribí la cantidad."})
            if p.unidad == Producto.UNIDAD and datos["cantidad"] != datos["cantidad"].to_integral_value():
                raise serializers.ValidationError({"cantidad": "Este producto se cuenta por unidad: escribí un número entero."})
        else:
            nombre = dict(Producto.PRESENTACIONES)[datos["presentacion"]].lower()
            medida = "kilos" if p.unidad == Producto.KG else "unidades"
            bultos = datos.get("bultos")
            if bultos is None or bultos <= 0:
                raise serializers.ValidationError({"bultos": f"Escribí cuántos se compraron ({Producto.PLURALES[datos['presentacion']]})."})
            # Si no se indica, vale lo que el producto tiene cargado en «Llega en»
            contenido = datos.get("contenido") or p.contenido
            if contenido is None or contenido <= 0:
                raise serializers.ValidationError({"contenido": f"Indicá cuántos {medida} trae cada {nombre}, aunque sea aproximado: hace falta para el stock."})
            if p.unidad == Producto.UNIDAD and contenido != contenido.to_integral_value():
                raise serializers.ValidationError({"contenido": f"Este producto va por unidad: cada {nombre} trae un número entero."})
            cantidad = (bultos * contenido).quantize(Decimal("0.001"))
            if p.unidad == Producto.UNIDAD and cantidad != cantidad.to_integral_value():
                raise serializers.ValidationError({"bultos": "El total tiene que dar un número entero de unidades."})
            datos["contenido"], datos["cantidad"] = contenido, cantidad
        if datos["pagado"] > datos["costo_total"]:
            raise serializers.ValidationError({"pagado": "No se puede pagar más de lo que costó."})

        if datos.get("producto") is None:
            # Se valida igual que un alta hecha desde Productos (nombre repetido, precio, categoría…)
            unitario = (datos["costo_total"] / datos["cantidad"]).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
            alta = ProductoSerializer(context=self.context, data={
                "nombre": nuevo.get("nombre", ""), "categoria": nuevo.get("categoria"), "unidad": nuevo.get("unidad"),
                "precio_venta": nuevo.get("precio_venta"), "precio_costo": str(unitario),
                # Si se compró por cajón, el producto nace sabiendo en qué llega
                "presentacion": datos["presentacion"],
                "contenido": None if datos["contenido"] is None else str(datos["contenido"]),
            })
            if not alta.is_valid():
                raise serializers.ValidationError({"producto_nuevo": alta.errors})
            datos["alta"] = alta
        return datos


class NuevoPagoSerializer(serializers.Serializer):
    importe = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=CENTAVOS,
        error_messages={"min_value": "El importe tiene que ser mayor a 0.", "required": "Escribí cuánto se paga.",
                        "invalid": "Escribí el importe con números."},
    )
    medio_pago = serializers.ChoiceField(
        choices=MEDIOS_DE_PAGO, default="EFECTIVO", error_messages={"invalid_choice": "Elegí con qué se paga."}
    )


# ---------- Reglas ----------

def pagar(compra, importe, medio_pago, usuario):
    """Anota un pago al comerciante. `compra` ya tiene que estar bloqueada."""
    PagoCompra.objects.create(
        compra=compra, importe=importe, medio_pago=medio_pago, usuario=usuario,
        turno=getattr(usuario, "turno_abierto", None),
    )
    compra.pagado += importe
    compra.save(update_fields=["pagado"])


def deuda_total():
    """Todo lo que hoy se les debe a los comerciantes."""
    total = Compra.objects.filter(anulada=False, pagado__lt=F("costo_total")).aggregate(
        t=Sum(F("costo_total") - F("pagado"))
    )["t"]
    return (total or Decimal(0)).quantize(CENTAVOS)


# ---------- Vistas ----------

class ComprasViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    GET  /api/compras/                lista (hasta 300). Filtros: ?estado=DEBE|PARCIAL|PAGADO  ?comerciante=  ?desde=&hasta=
    POST /api/compras/                anotar una compra {comerciante, producto, cantidad, costo_total, pagado?, medio_pago?, sumar_stock?, nota?}
    GET  /api/compras/{id}/
    POST /api/compras/{id}/pago/      pagarle al comerciante {importe, medio_pago?}
    POST /api/compras/{id}/anular/    {motivo}
    """

    serializer_class = CompraSerializer
    permission_classes = [EsEncargadoOAdministrador, PasswordAlDia]
    queryset = Compra.objects.select_related(
        "comerciante", "producto__categoria__seccion", "usuario", "anulada_por"
    ).prefetch_related("pagos__usuario")

    def list(self, request):
        qs = self.get_queryset()
        p = request.query_params
        estado = p.get("estado")
        if estado == Compra.DEBE:
            qs = qs.filter(anulada=False, pagado=0)
        elif estado == Compra.PARCIAL:
            qs = qs.filter(anulada=False, pagado__gt=0, pagado__lt=F("costo_total"))
        elif estado == Compra.PAGADO:
            qs = qs.filter(anulada=False, pagado__gte=F("costo_total"))
        if p.get("comerciante", "").isdigit():
            qs = qs.filter(comerciante_id=p["comerciante"])
        try:
            if p.get("desde"):
                qs = qs.filter(fecha_hora__gte=inicio_del_dia(date.fromisoformat(p["desde"])))
            if p.get("hasta"):
                qs = qs.filter(fecha_hora__lt=inicio_del_dia(date.fromisoformat(p["hasta"]) + timedelta(days=1)))
        except ValueError:
            return error("Las fechas deben tener el formato AAAA-MM-DD.")

        # Cuánto se le debe a cada comerciante (de todas sus compras, no solo de las filtradas)
        deudas = {
            fila["comerciante"]: fila["t"]
            for fila in Compra.objects.filter(anulada=False, pagado__lt=F("costo_total"))
            .values("comerciante").annotate(t=Sum(F("costo_total") - F("pagado")))
        }
        comerciantes = [
            {"id": c.id, "nombre": c.nombre, "deuda": str((deudas.get(c.id) or Decimal(0)).quantize(CENTAVOS))}
            for c in Comerciante.objects.all()
        ]
        return Response({
            "deuda_total": str(deuda_total()),
            "comerciantes": comerciantes,
            "compras": self.get_serializer(qs[:MAXIMO], many=True).data,
        })

    def responder(self, compra, codigo=status.HTTP_200_OK):
        return Response(self.get_serializer(self.get_queryset().get(pk=compra.pk)).data, status=codigo)

    def create(self, request):
        datos = NuevaCompraSerializer(data=request.data, context={"request": request})
        datos.is_valid(raise_exception=True)
        d = datos.validated_data
        with transaction.atomic():
            producto = d.get("producto")
            if producto is None:  # RF-122: lo comprado no existía, se da de alta acá mismo
                producto = d["alta"].save(creado_por=request.user)
                CambioProducto.objects.create(
                    producto=producto, realizado_por=request.user, accion=CambioProducto.ALTA,
                    detalle=f"Venta ${producto.precio_venta} · Costo ${producto.precio_costo} · creado al anotar una compra",
                )
            # La base no distingue mayúsculas ni acentos: «La Paulina» = «la paulina»
            comerciante = Comerciante.objects.filter(nombre=d["comerciante"]).first()
            if comerciante is None:
                comerciante = Comerciante.objects.create(nombre=d["comerciante"], creado_por=request.user)
            unitario = (d["costo_total"] / d["cantidad"]).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
            compra = Compra.objects.create(
                comerciante=comerciante, producto=producto, nombre_producto=producto.nombre, unidad=producto.unidad,
                cantidad=d["cantidad"], presentacion=d["presentacion"], bultos=d["bultos"], contenido=d["contenido"],
                costo_total=d["costo_total"], costo_unitario=unitario,
                sumo_stock=d["sumar_stock"], nota=" ".join(d.get("nota", "").split())[:200] or None,
                usuario=request.user, turno=getattr(request.user, "turno_abierto", None),
            )
            if d["sumar_stock"]:  # RF-114: la compra suma la mercadería al stock, al costo de esta compra
                # Si el producto estaba como «suelto» y se compró por cajón, queda anotado en el producto
                recordar_presentacion(producto, d["presentacion"], d["contenido"], request.user)
                motivo = f"Compra N° {compra.numero} a {comerciante.nombre}"
                if compra.por_bulto:
                    motivo += f" · {compra.presentacion_texto}"  # queda anotado cómo llegó: «2 cajones × 18 kg»
                registrar_movimiento(
                    producto.pk, request.user, MovimientoStock.INGRESO, lambda p: (d["cantidad"], unitario, motivo),
                )
            if d["pagado"] > 0:
                pagar(compra, d["pagado"], d["medio_pago"], request.user)
        return self.responder(compra, status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def pago(self, request, pk=None):
        """Se le paga al comerciante lo que falta, o una parte (RF-116)."""
        datos = NuevoPagoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        d = datos.validated_data
        with transaction.atomic():
            compra = Compra.objects.select_for_update().filter(pk=pk).first()
            if compra is None:
                return error("La compra no existe.", status.HTTP_404_NOT_FOUND)
            if compra.anulada:
                return error("Esta compra está anulada: no se le pueden cargar pagos.")
            if compra.falta <= 0:
                return error("Esta compra ya está pagada.")
            if d["importe"] > compra.falta:
                return error(f"Solo faltan pagar ${compra.falta}: no se puede pagar más que eso.")
            pagar(compra, d["importe"], d["medio_pago"], request.user)
        return self.responder(compra)

    @action(detail=True, methods=["post"])
    def anular(self, request, pk=None):
        """La compra se anotó mal. Queda en la lista como anulada y, si había sumado stock, se lo vuelve a restar."""
        motivo = str(request.data.get("motivo") or "").strip()[:200]
        if not motivo:
            return error("Indicá el motivo de la anulación.")
        with transaction.atomic():
            compra = Compra.objects.select_for_update().select_related("comerciante").filter(pk=pk).first()
            if compra is None:
                return error("La compra no existe.", status.HTTP_404_NOT_FOUND)
            if compra.anulada:
                return error("Esta compra ya estaba anulada.")
            if compra.sumo_stock:
                registrar_movimiento(
                    compra.producto_id, request.user, MovimientoStock.INGRESO,
                    lambda p: (-compra.cantidad, compra.costo_unitario,
                               f"Anulación de la compra N° {compra.numero} ({texto_cantidad(compra.cantidad)}): {motivo}"),
                )
            compra.anulada = True
            compra.anulada_por = request.user
            compra.anulada_en = timezone.now()
            compra.motivo_anulacion = motivo
            compra.save(update_fields=["anulada", "anulada_por", "anulada_en", "motivo_anulacion"])
        return self.responder(compra)
