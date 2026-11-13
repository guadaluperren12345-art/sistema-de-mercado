"""API de ventas y recibos.

Vender: todos los usuarios con sesión (los precios se toman del sistema, no de lo que envía la pantalla).
Ver recibos: dueños y encargados ven todos; un empleado ve solo los suyos.
Modificar una compra ya pagada: el cajero, sus propias ventas del día; dueños y encargados, cualquiera.
Anular: dueños y encargados (matriz de permisos 4.3).
"""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from clientes import servicios as cuentas
from productos.api import inicio_del_dia, texto_cantidad
from productos.models import MovimientoStock, Producto
from usuarios.permisos import EsEncargadoOAdministrador, PasswordAlDia

from .models import DetalleVenta, Venta

CENTAVOS = Decimal("0.01")
MAXIMO = 500


class ErrorDeVenta(Exception):
    """Algo de la venta no se puede hacer. El mensaje se le muestra tal cual al cajero."""


def error(mensaje, codigo=status.HTTP_400_BAD_REQUEST):
    return Response({"detail": str(mensaje)}, status=codigo)


def ve_todo(usuario):
    return usuario.es_administrador or usuario.es_encargado


def puede_corregir(usuario, venta):
    """Una compra pagada la puede modificar quien la cobró, el mismo día; o un encargado o dueño."""
    if venta.anulada:
        return False
    if ve_todo(usuario):
        return True
    return venta.usuario_id == usuario.id and timezone.localtime(venta.fecha_hora).date() == timezone.localdate()


# ---------- Serializers ----------

class ItemSerializer(serializers.Serializer):
    producto = serializers.IntegerField()
    cantidad = serializers.DecimalField(max_digits=12, decimal_places=3)


class NuevaVentaSerializer(serializers.Serializer):
    items = ItemSerializer(many=True, allow_empty=False, error_messages={"empty": "La venta no tiene productos."})
    medio_pago = serializers.ChoiceField(
        choices=Venta.MEDIOS, error_messages={"invalid_choice": "Elegí cómo paga el cliente."}
    )
    paga_con = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True)
    # A quién se le anota, cuando el medio de pago es cuenta corriente
    cliente = serializers.IntegerField(required=False, allow_null=True)


class DetalleSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetalleVenta
        fields = ["producto", "nombre", "unidad", "cantidad", "precio_unitario", "subtotal"]  # sin el costo


class VentaSerializer(serializers.ModelSerializer):
    vendedor = serializers.CharField(source="usuario.nombre_completo")
    medio_pago_texto = serializers.CharField(source="get_medio_pago_display")
    anulada_por = serializers.SerializerMethodField()
    items = DetalleSerializer(source="detalles", many=True)
    # Si esta venta es la corrección de otra: número y total de la anterior
    corrige_a = serializers.SerializerMethodField()
    # Si esta venta fue modificada: número del recibo que la reemplazó
    reemplazada_por = serializers.SerializerMethodField()
    puede_corregir = serializers.SerializerMethodField()
    # A quién se le fió (null si se pagó en el momento)
    cliente = serializers.SerializerMethodField()

    class Meta:
        model = Venta
        fields = [
            "id", "numero", "fecha_hora", "vendedor", "medio_pago", "medio_pago_texto", "total", "paga_con",
            "vuelto", "en_buzon", "anulada", "anulada_por", "anulada_en", "motivo_anulacion",
            "corrige_a", "reemplazada_por", "puede_corregir", "cliente", "items",
        ]

    def get_cliente(self, venta):
        return {"id": venta.cliente_id, "nombre": venta.cliente.nombre} if venta.cliente_id else None

    def get_anulada_por(self, venta):
        return venta.anulada_por.nombre_completo if venta.anulada_por else None

    def get_corrige_a(self, venta):
        anterior = venta.corrige_a
        return {"id": anterior.id, "numero": anterior.numero, "total": str(anterior.total),
                "medio_pago": anterior.medio_pago} if anterior else None

    def get_reemplazada_por(self, venta):
        nueva = next(iter(venta.correcciones.all()), None)
        return {"id": nueva.id, "numero": nueva.numero} if nueva else None

    def get_puede_corregir(self, venta):
        return puede_corregir(self.context["request"].user, venta)


# ---------- Reglas ----------

def mover_stock(producto, cantidad, usuario, motivo, costo=None):
    """Movimiento de stock de una venta (negativo) o de su devolución (positivo). El producto ya está bloqueado."""
    producto.stock_actual += cantidad
    producto.save(update_fields=["stock_actual"])
    MovimientoStock.objects.create(
        producto=producto, tipo=MovimientoStock.VENTA, cantidad=cantidad,
        stock_resultante=producto.stock_actual,
        costo_unitario=producto.precio_costo if costo is None else costo,
        motivo=motivo[:200], usuario=usuario, turno=getattr(usuario, "turno_abierto", None),
    )


def sumar_items(items):
    """{producto: cantidad}, en el orden en que se cargaron. Si un producto vino en dos renglones, se suman."""
    cantidades = {}
    for item in items:
        cantidades[item["producto"]] = cantidades.get(item["producto"], Decimal(0)) + item["cantidad"]
    return cantidades


def bloquear_productos(ids):
    """Bloquea los productos (siempre en el mismo orden) para que dos cajas no pisen el stock."""
    return {p.pk: p for p in Producto.objects.select_for_update().filter(pk__in=ids).order_by("pk")}


def devolver_al_stock(venta, productos, usuario, motivo):
    """La mercadería de una venta vuelve al stock, al costo que tenía cuando se vendió."""
    for d in venta.detalles.all():
        mover_stock(productos[d.producto_id], d.cantidad, usuario, motivo, costo=d.costo_unitario)


def cobrar(usuario, cantidades, productos, medio_pago, paga_con=None, corrige_a=None, cliente_id=None):
    """Crea la venta con sus renglones y descuenta el stock (RF-39, RF-40). Devuelve (venta, avisos).

    Debe llamarse dentro de una transacción, con los productos ya bloqueados.
    """
    if any(pk not in productos for pk in cantidades):
        raise ErrorDeVenta("Uno de los productos ya no existe. Volvé a cargar la venta.")

    renglones = []
    for pk, cantidad in cantidades.items():  # en el orden en que se cargaron: así sale el recibo
        p = productos[pk]
        if not p.activo:
            raise ErrorDeVenta(f"«{p.nombre}» está dado de baja y no se puede vender.")
        if cantidad <= 0:
            raise ErrorDeVenta(f"La cantidad de «{p.nombre}» tiene que ser mayor a 0.")
        if p.unidad == Producto.UNIDAD and cantidad != cantidad.to_integral_value():
            raise ErrorDeVenta(f"«{p.nombre}» se vende por unidad: la cantidad tiene que ser un número entero.")
        subtotal = (cantidad * p.precio_venta).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
        renglones.append((p, cantidad, subtotal))

    total = sum(r[2] for r in renglones)
    if medio_pago != Venta.EFECTIVO:
        paga_con = None
    if paga_con is not None and paga_con < total:
        raise ErrorDeVenta("El cliente paga con menos plata que el total.")

    # Fiado: tiene que haber un cliente y no pasarse de su límite (RF-99, RF-100)
    cliente = None
    if medio_pago == Venta.CUENTA:
        try:
            cliente = cuentas.cliente_para_fiar(cliente_id, total)
        except cuentas.ErrorDeCuenta as e:
            raise ErrorDeVenta(str(e))

    venta = Venta.objects.create(
        usuario=usuario, turno=getattr(usuario, "turno_abierto", None), medio_pago=medio_pago, total=total,
        paga_con=paga_con, vuelto=None if paga_con is None else paga_con - total, corrige_a=corrige_a,
        cliente=cliente,
    )
    if cliente:
        cuentas.anotar_compra(cliente, venta, usuario)
    avisos = []
    for p, cantidad, subtotal in renglones:
        DetalleVenta.objects.create(
            venta=venta, producto=p, nombre=p.nombre, unidad=p.unidad, cantidad=cantidad,
            precio_unitario=p.precio_venta, costo_unitario=p.precio_costo, subtotal=subtotal,
        )
        # Si no alcanzaba el stock, se vende igual y se avisa (queda en rojo)
        faltaba = p.stock_actual < cantidad
        mover_stock(p, -cantidad, usuario, f"Venta N° {venta.numero}")
        if faltaba:
            avisos.append(
                f"«{p.nombre}» no tenía stock suficiente en el sistema: quedó en "
                f"{texto_cantidad(p.stock_actual)}. Avisá para que hagan un recuento."
            )
    return venta, avisos


# ---------- Vistas ----------

class VentasViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    POST /api/ventas/                 cobrar una venta {items: [{producto, cantidad}], medio_pago, paga_con?}
    GET  /api/ventas/                 buzón de recibos. Filtros: ?desde=&hasta= (AAAA-MM-DD)  ?todas=1 (dueños: también las que ya salieron del buzón)
    GET  /api/ventas/{id}/            un recibo
    POST /api/ventas/{id}/corregir/   modificar una compra ya pagada {items, medio_pago}: agrega o saca productos
    POST /api/ventas/{id}/anular/     {motivo} — devuelve toda la mercadería al stock
    GET  /api/ventas/hoy/             total vendido hoy, por sección y por medio de pago (dueños y encargados)
    """

    serializer_class = VentaSerializer

    def get_permissions(self):
        if self.action in ("anular", "hoy"):
            return [EsEncargadoOAdministrador(), PasswordAlDia()]
        return super().get_permissions()

    def get_queryset(self):
        usuario = self.request.user
        qs = Venta.objects.select_related("usuario", "anulada_por", "corrige_a", "cliente").prefetch_related("detalles", "correcciones")
        if not ve_todo(usuario):
            qs = qs.filter(usuario=usuario)
        if self.action != "list":
            return qs

        p = self.request.query_params
        if not (p.get("todas") == "1" and usuario.es_administrador):
            qs = qs.filter(en_buzon=True)
        try:
            if p.get("desde"):
                qs = qs.filter(fecha_hora__gte=inicio_del_dia(date.fromisoformat(p["desde"])))
            if p.get("hasta"):
                qs = qs.filter(fecha_hora__lt=inicio_del_dia(date.fromisoformat(p["hasta"]) + timedelta(days=1)))
        except ValueError:
            raise serializers.ValidationError({"detail": "Las fechas deben tener el formato AAAA-MM-DD."})
        return qs[:MAXIMO]

    def recibo(self, venta, avisos, codigo=status.HTTP_200_OK):
        venta = self.get_queryset().get(pk=venta.pk)
        return Response({**self.get_serializer(venta).data, "avisos": avisos}, status=codigo)

    def create(self, request):
        datos = NuevaVentaSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        d = datos.validated_data
        cantidades = sumar_items(d["items"])
        try:
            with transaction.atomic():
                venta, avisos = cobrar(request.user, cantidades, bloquear_productos(cantidades),
                                       d["medio_pago"], d.get("paga_con"), cliente_id=d.get("cliente"))
        except ErrorDeVenta as e:
            return error(e)
        return self.recibo(venta, avisos, status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def corregir(self, request, pk=None):
        """Modifica una compra ya pagada: el cliente se olvidó algo, o quiere sacar o cambiar un producto.

        La venta original no se toca ni se borra: queda anulada como «reemplazada» y se crea una venta
        nueva con los productos corregidos, enlazada a la anterior. Así el recibo viejo sigue existiendo
        y se ve quién cambió qué. La diferencia entre los dos totales es lo que hay que cobrar o devolver.
        """
        datos = NuevaVentaSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        d = datos.validated_data
        cantidades = sumar_items(d["items"])
        try:
            with transaction.atomic():
                anterior = Venta.objects.select_for_update().filter(pk=pk).first()
                # Un empleado no tiene que poder saber si existe una venta ajena: mismo 404
                if anterior is None or not (ve_todo(request.user) or anterior.usuario_id == request.user.id):
                    return error("La venta no existe.", status.HTTP_404_NOT_FOUND)
                if anterior.anulada:
                    raise ErrorDeVenta("Esta venta ya fue anulada o modificada: no se puede cambiar.")
                if not puede_corregir(request.user, anterior):
                    raise ErrorDeVenta("Solo podés modificar tus ventas de hoy. Pedile a un encargado.")

                detalles = {det.producto_id: det.cantidad for det in anterior.detalles.all()}
                cliente_id = d.get("cliente") or anterior.cliente_id
                mismo_cliente = d["medio_pago"] != Venta.CUENTA or cliente_id == anterior.cliente_id
                if detalles == cantidades and anterior.medio_pago == d["medio_pago"] and mismo_cliente:
                    raise ErrorDeVenta("No cambiaste nada de la compra.")

                productos = bloquear_productos(set(detalles) | set(cantidades))
                # Primero vuelve todo lo anterior al stock y después se descuenta lo nuevo
                devolver_al_stock(anterior, productos, request.user, f"Modificación de la venta N° {anterior.numero}")
                # Si era fiada, primero sale de la deuda del cliente; la versión corregida se anota de nuevo
                cuentas.deshacer_compra(anterior, request.user, f"Modificación de la venta N° {anterior.numero}")
                venta, avisos = cobrar(request.user, cantidades, productos, d["medio_pago"], corrige_a=anterior,
                                       cliente_id=cliente_id)

                anterior.anulada = True
                anterior.anulada_por = request.user
                anterior.anulada_en = timezone.now()
                anterior.motivo_anulacion = f"Compra modificada: la reemplaza el recibo N° {venta.numero}"
                anterior.save(update_fields=["anulada", "anulada_por", "anulada_en", "motivo_anulacion"])
        except ErrorDeVenta as e:
            return error(e)
        return self.recibo(venta, avisos, status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def anular(self, request, pk=None):
        motivo = str(request.data.get("motivo") or "").strip()[:200]
        if not motivo:
            return error("Indicá el motivo de la anulación.")
        with transaction.atomic():
            venta = Venta.objects.select_for_update().filter(pk=pk).first()
            if venta is None:
                return error("La venta no existe.", status.HTTP_404_NOT_FOUND)
            if venta.anulada:
                return error("Esta venta ya estaba anulada.")
            productos = bloquear_productos({d.producto_id for d in venta.detalles.all()})
            devolver_al_stock(venta, productos, request.user, f"Anulación de la venta N° {venta.numero}: {motivo}")
            cuentas.deshacer_compra(venta, request.user, f"Anulación de la venta N° {venta.numero}: {motivo}")
            venta.anulada = True
            venta.anulada_por = request.user
            venta.anulada_en = timezone.now()
            venta.motivo_anulacion = motivo
            venta.save(update_fields=["anulada", "anulada_por", "anulada_en", "motivo_anulacion"])
        return self.recibo(venta, [])

    @action(detail=False, methods=["get"])
    def hoy(self, request):
        """RF-41: lo vendido hoy, siempre a la vista."""
        from turnos import servicios

        hoy = timezone.localdate()
        return Response(servicios.resumen_de_ventas(*servicios.rango_de_fechas(hoy, hoy)))
