"""API de secciones, categorías, productos y stock.

Ver productos y stock: todos los usuarios con sesión (los empleados los necesitan para vender).
Alta, baja, nuevas categorías y movimientos de stock: dueños y encargados (matriz de permisos 4.3).
El precio de costo solo lo ven dueños y encargados.
"""

import re
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from usuarios.permisos import EsEncargadoOAdministrador, PasswordAlDia

from .models import CambioProducto, Categoria, MovimientoStock, Producto, Seccion


def puede_gestionar(usuario):
    return usuario.es_administrador or usuario.es_encargado


def error(mensaje):
    return Response({"detail": mensaje}, status=status.HTTP_400_BAD_REQUEST)


# ---------- Serializers ----------

class CategoriaSerializer(serializers.ModelSerializer):
    seccion = serializers.PrimaryKeyRelatedField(
        queryset=Seccion.objects.all(), error_messages={"does_not_exist": "La sección no existe."}
    )

    class Meta:
        model = Categoria
        fields = ["id", "seccion", "nombre"]
        validators = []  # la unicidad se valida abajo con un mensaje en español

    def validate_nombre(self, valor):
        valor = " ".join(valor.split())
        if len(valor) < 2:
            raise serializers.ValidationError("Escribí un nombre de al menos 2 letras.")
        return valor[0].upper() + valor[1:]

    def validate(self, datos):
        # La base usa collation sin distinguir mayúsculas ni acentos: "Pollo" = "pollo"
        if Categoria.objects.filter(seccion=datos["seccion"], nombre=datos["nombre"]).exists():
            raise serializers.ValidationError({"nombre": "Esa categoría ya existe en la sección."})
        return datos


class SeccionSerializer(serializers.ModelSerializer):
    categorias = serializers.SerializerMethodField()

    class Meta:
        model = Seccion
        fields = ["id", "nombre", "categorias"]

    def get_categorias(self, seccion):
        return [{"id": c.id, "nombre": c.nombre} for c in seccion.categorias.all()]


class ProductoSerializer(serializers.ModelSerializer):
    seccion = serializers.CharField(source="categoria.seccion.nombre", read_only=True)
    seccion_id = serializers.IntegerField(source="categoria.seccion_id", read_only=True)
    categoria_nombre = serializers.CharField(source="categoria.nombre", read_only=True)
    categoria = serializers.PrimaryKeyRelatedField(
        queryset=Categoria.objects.all(), error_messages={"does_not_exist": "La categoría no existe."}
    )
    precio_venta = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0.01"),
        error_messages={"min_value": "El precio de venta tiene que ser mayor a 0."},
    )
    precio_costo = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0"),
        error_messages={"min_value": "El precio de costo no puede ser negativo."},
    )

    stock_minimo = serializers.DecimalField(
        max_digits=12, decimal_places=3, min_value=Decimal("0"), required=False,
        error_messages={"min_value": "El stock mínimo no puede ser negativo."},
    )
    semaforo = serializers.CharField(read_only=True)
    contenido = serializers.DecimalField(max_digits=12, decimal_places=3, required=False, allow_null=True)
    presentacion_texto = serializers.CharField(read_only=True)

    class Meta:
        model = Producto
        fields = [
            "id", "nombre", "codigo", "codigo_barras", "seccion", "seccion_id", "categoria", "categoria_nombre",
            "unidad", "presentacion", "contenido", "presentacion_texto",
            "precio_venta", "precio_costo", "stock_actual", "stock_minimo", "semaforo",
            "activo", "fecha_creacion",
        ]
        # El stock no se escribe a mano (RN-09): solo cambia con movimientos
        read_only_fields = ["stock_actual", "activo", "fecha_creacion"]
        validators = []  # la unicidad del código se valida en validate_codigo con un mensaje claro
        extra_kwargs = {
            "codigo": {"required": False, "allow_null": True, "allow_blank": True, "validators": []},
            "codigo_barras": {"required": False, "allow_null": True, "allow_blank": True, "validators": []},
            "unidad": {"error_messages": {"invalid_choice": "Elegí si se vende por unidad o por kilo."}},
            "presentacion": {"error_messages": {"invalid_choice": "Elegí cómo llega: suelto, caja, cajón, bandeja…"}},
        }

    def to_representation(self, producto):
        datos = super().to_representation(producto)
        if not puede_gestionar(self.context["request"].user):
            datos.pop("precio_costo")  # el costo no lo ven los empleados
        return datos

    def validate_nombre(self, valor):
        valor = " ".join(valor.split())
        if len(valor) < 2:
            raise serializers.ValidationError("Escribí un nombre de al menos 2 letras.")
        return valor[0].upper() + valor[1:]

    def validar_codigo(self, valor):
        """Número de producto y código de barras comparten las reglas: al escanear o tipear en la venta
        se busca en los dos, así que un mismo código no puede identificar a dos productos distintos."""
        valor = (valor or "").strip()
        if not valor:
            return None
        if not re.fullmatch(r"[A-Za-z0-9-]{1,30}", valor):
            raise serializers.ValidationError("El código solo puede tener letras, números y guiones (hasta 30).")
        existente = self.otros_productos().filter(Q(codigo=valor) | Q(codigo_barras=valor)).first()
        if existente:
            estado = "" if existente.activo else " (dado de baja)"
            raise serializers.ValidationError(f"Ese código ya lo tiene «{existente.nombre}»{estado}.")
        return valor

    def validate_codigo(self, valor):
        return self.validar_codigo(valor)

    def validate_codigo_barras(self, valor):
        return self.validar_codigo(valor)

    def otros_productos(self):
        """Productos contra los que se controla que no se repitan nombre y código (sin contar el que se edita)."""
        qs = Producto.objects.all()
        return qs.exclude(pk=self.instance.pk) if self.instance else qs

    def validate(self, datos):
        # No repetir el nombre dentro de la misma sección (aunque esté dado de baja)
        categoria = datos.get("categoria", getattr(self.instance, "categoria", None))
        nombre = datos.get("nombre", getattr(self.instance, "nombre", None))
        existente = self.otros_productos().filter(categoria__seccion_id=categoria.seccion_id, nombre=nombre).first()
        if existente:
            estado = " Está dado de baja: podés reactivarlo." if not existente.activo else ""
            raise serializers.ValidationError({"nombre": f"Ya existe un producto con ese nombre en la sección.{estado}"})
        numero = datos.get("codigo", getattr(self.instance, "codigo", None))
        barras = datos.get("codigo_barras", getattr(self.instance, "codigo_barras", None))
        if numero and barras and numero == barras:
            raise serializers.ValidationError({"codigo": "El número de producto y el código de barras no pueden ser iguales."})

        # Presentación en la que llega: si no es suelto, hay que saber cuánto trae cada una
        presentacion = datos.get("presentacion", getattr(self.instance, "presentacion", Producto.SUELTO))
        contenido = datos.get("contenido", getattr(self.instance, "contenido", None))
        unidad = datos.get("unidad", getattr(self.instance, "unidad", Producto.UNIDAD))
        if presentacion == Producto.SUELTO:
            if self.instance is None or "presentacion" in datos or "contenido" in datos:
                datos["contenido"] = None
        else:
            nombre = dict(Producto.PRESENTACIONES)[presentacion].lower()
            if contenido is None or contenido <= 0:
                raise serializers.ValidationError({"contenido": f"Indicá cuánto trae cada {nombre}."})
            if unidad == Producto.UNIDAD and contenido != contenido.to_integral_value():
                raise serializers.ValidationError({"contenido": f"Este producto va por unidad: cada {nombre} trae un número entero."})
        return datos


class ProductoEdicionSerializer(ProductoSerializer):
    """Corrección de datos de un producto: nombre, código, categoría y unidad.

    Los precios no se cambian acá: eso es el módulo de precios (etapa 6), con sus propias reglas.
    """

    precio_venta = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    precio_costo = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    CAMPOS = {"nombre": "Nombre", "codigo": "Número", "codigo_barras": "Código de barras",
              "categoria": "Categoría", "unidad": "Unidad", "presentacion": "Llega en",
              "stock_minimo": "Stock mínimo"}

    def describir_cambios(self, antes, despues):
        """Texto para la auditoría: «Nombre: Pechga → Pechuga · Código: — → 101»."""
        cambios = []
        for campo, titulo in self.CAMPOS.items():
            a, d = antes[campo], despues[campo]
            if a != d:
                cambios.append(f"{titulo}: {a or '—'} → {d or '—'}")
        return " · ".join(cambios)


# ---------- Vistas ----------

class SeccionesViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """GET /api/secciones/ — las 3 secciones con sus categorías."""

    queryset = Seccion.objects.prefetch_related("categorias")
    serializer_class = SeccionSerializer
    pagination_class = None


class CategoriasViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    """POST /api/categorias/  {seccion, nombre} — nueva categoría (dueños y encargados)."""

    queryset = Categoria.objects.all()
    serializer_class = CategoriaSerializer
    permission_classes = [EsEncargadoOAdministrador, PasswordAlDia]


def foto(producto):
    """Datos corregibles de un producto, como texto, para comparar antes y después de editar."""
    return {
        "nombre": producto.nombre,
        "codigo": producto.codigo,
        "codigo_barras": producto.codigo_barras,
        "categoria": str(producto.categoria),
        "unidad": producto.get_unidad_display(),
        "presentacion": producto.presentacion_texto,
        "stock_minimo": texto_cantidad(producto.stock_minimo),
    }


def texto_cantidad(cantidad):
    """Decimal → texto sin ceros de más y con coma: 5.000 → «5», 1.250 → «1,25»."""
    return f"{Decimal(cantidad).normalize():f}".replace(".", ",")


# ---------- Stock: movimientos ----------

class CantidadSerializer(serializers.Serializer):
    """Cantidad de un movimiento. Los productos por unidad no admiten decimales."""

    campo = "cantidad"
    minimo = Decimal("0.001")

    def __init__(self, *args, producto, **kwargs):
        super().__init__(*args, **kwargs)
        self.producto = producto

    def validar_cantidad(self, valor):
        if valor < self.minimo:
            raise serializers.ValidationError("La cantidad tiene que ser mayor a 0.")
        if self.producto.unidad == Producto.UNIDAD and valor != valor.to_integral_value():
            raise serializers.ValidationError("Este producto se cuenta por unidad: escribí un número entero.")
        return valor

    def leer_bultos(self, datos, minimo=Decimal("0.001")):
        """La cantidad vino por caja, cajón, bandeja…: `bultos` (cuántos), y opcionalmente `presentacion`
        y `contenido` si no son los que el producto tiene cargados en «Llega en» (RF-121).

        Devuelve (total en unidades o kilos, «3 cajones × 18 kg») y deja en `datos` la presentación
        y el contenido que se usaron. Devuelve None si la cantidad vino suelta.
        """
        p = self.producto
        bultos = datos.get("bultos")
        if bultos is None:
            return None
        presentacion = datos.get("presentacion") or Producto.SUELTO
        if presentacion == Producto.SUELTO:
            presentacion = p.presentacion
        if presentacion == Producto.SUELTO:
            raise serializers.ValidationError({"bultos": "Elegí en qué viene: caja, cajón, bandeja, bolsa, pack o bulto."})
        if bultos < 0 or (bultos == 0 and minimo > 0):
            raise serializers.ValidationError({"bultos": "La cantidad tiene que ser mayor a 0."})
        contenido = datos.get("contenido") or p.contenido
        nombre = dict(Producto.PRESENTACIONES)[presentacion].lower()
        if contenido is None or contenido <= 0:
            raise serializers.ValidationError({"contenido": f"Indicá cuánto trae cada {nombre}."})
        if p.unidad == Producto.UNIDAD and contenido != contenido.to_integral_value():
            raise serializers.ValidationError({"contenido": f"Este producto va por unidad: cada {nombre} trae un número entero."})
        total = (bultos * contenido).quantize(Decimal("0.001"))
        if p.unidad == Producto.UNIDAD and total != total.to_integral_value():
            raise serializers.ValidationError({"bultos": "Este producto se cuenta por unidad: el total tiene que dar un número entero."})
        if bultos != 1:
            nombre = Producto.PLURALES[presentacion]
        datos["presentacion"], datos["contenido"] = presentacion, contenido
        medida = "kg" if p.unidad == Producto.KG else "u."
        return total, f"{texto_cantidad(bultos)} {nombre} × {texto_cantidad(contenido)} {medida}"


CAMPO_PRESENTACION = dict(
    choices=Producto.PRESENTACIONES, required=False,
    error_messages={"invalid_choice": "Elegí en qué viene: suelto, caja, cajón, bandeja…"},
)


def recordar_presentacion(producto, presentacion, contenido, usuario):
    """Si el producto estaba cargado como «suelto» y ahora llegó en cajón (o caja, bandeja…), queda anotado
    en el producto, así el stock también se puede ver en cajones y la próxima vez ya viene propuesto."""
    if producto.presentacion != Producto.SUELTO or not presentacion or presentacion == Producto.SUELTO or not contenido:
        return
    antes = producto.presentacion_texto
    producto.presentacion, producto.contenido = presentacion, contenido
    producto.save(update_fields=["presentacion", "contenido"])
    CambioProducto.objects.create(
        producto=producto, realizado_por=usuario, accion=CambioProducto.EDICION,
        detalle=f"Llega en: {antes} → {producto.presentacion_texto}",
    )


class IngresoSerializer(CantidadSerializer):
    """Mercadería que llega. Se carga de una de dos formas:

    - suelta: `cantidad` en unidades o kilos;
    - por caja, cajón, bandeja…: `bultos` (cuántos llegaron) y, si esta vez traen otra cantidad
      que la habitual del producto, `contenido`. El sistema calcula la cantidad.
    """

    cantidad = serializers.DecimalField(max_digits=12, decimal_places=3, required=False)
    bultos = serializers.DecimalField(max_digits=10, decimal_places=3, required=False, allow_null=True)
    contenido = serializers.DecimalField(max_digits=12, decimal_places=3, required=False, allow_null=True)
    # En qué llegó esta vez, si no es lo que el producto tiene cargado (o si estaba como «suelto»)
    presentacion = serializers.ChoiceField(**CAMPO_PRESENTACION)
    costo_unitario = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0"), required=False, allow_null=True,
        error_messages={"min_value": "El costo no puede ser negativo."},
    )
    # Lo que costó cada caja o cajón: el sistema saca el costo por unidad o por kilo
    costo_bulto = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0"), required=False, allow_null=True,
        error_messages={"min_value": "El costo no puede ser negativo."},
    )
    motivo = serializers.CharField(max_length=200, required=False, allow_blank=True)

    def validate_cantidad(self, valor):
        return self.validar_cantidad(valor)

    def validate(self, datos):
        por_bulto = self.leer_bultos(datos)
        if por_bulto is None:
            datos.pop("presentacion", None)  # llegó suelto: no hay nada que recordar
            if datos.get("cantidad") is None:
                raise serializers.ValidationError({"cantidad": "Indicá cuánto llegó."})
            return datos

        datos["cantidad"], detalle = por_bulto
        if datos.get("costo_bulto") is not None and datos.get("costo_unitario") is None:
            datos["costo_unitario"] = (datos["costo_bulto"] / datos["contenido"]).quantize(Decimal("0.01"))
        # Queda anotado cómo llegó: «3 cajones × 18 kg»
        datos["motivo"] = " · ".join(t for t in (detalle, (datos.get("motivo") or "").strip()) if t)[:200]
        return datos


class PerdidaSerializer(CantidadSerializer):
    """Lo que se perdió: `cantidad` suelta, o `bultos` (+ `presentacion` y `contenido`) si se perdió un cajón entero."""

    cantidad = serializers.DecimalField(max_digits=12, decimal_places=3, required=False)
    bultos = serializers.DecimalField(max_digits=10, decimal_places=3, required=False, allow_null=True)
    contenido = serializers.DecimalField(max_digits=12, decimal_places=3, required=False, allow_null=True)
    presentacion = serializers.ChoiceField(**CAMPO_PRESENTACION)
    motivo = serializers.CharField(
        max_length=200, error_messages={"blank": "Indicá el motivo de la pérdida.", "required": "Indicá el motivo de la pérdida."}
    )

    def validate_cantidad(self, valor):
        return self.validar_cantidad(valor)

    def validate(self, datos):
        por_bulto = self.leer_bultos(datos)
        if por_bulto is not None:
            datos["cantidad"], detalle = por_bulto
            datos["motivo"] = f"{datos['motivo']} · {detalle}"[:200]
        elif datos.get("cantidad") is None:
            raise serializers.ValidationError({"cantidad": "Indicá cuánto se perdió."})
        return datos


class AjusteSerializer(CantidadSerializer):
    """Recuento: `stock_real` en unidades o kilos, o `bultos` (+ `presentacion` y `contenido`) si se contó por cajones."""

    minimo = Decimal("0")
    stock_real = serializers.DecimalField(max_digits=12, decimal_places=3, required=False)
    bultos = serializers.DecimalField(max_digits=10, decimal_places=3, required=False, allow_null=True)
    contenido = serializers.DecimalField(max_digits=12, decimal_places=3, required=False, allow_null=True)
    presentacion = serializers.ChoiceField(**CAMPO_PRESENTACION)
    motivo = serializers.CharField(
        max_length=200, error_messages={"blank": "Indicá el motivo del ajuste.", "required": "Indicá el motivo del ajuste."}
    )

    def validate_stock_real(self, valor):
        if valor < 0:
            raise serializers.ValidationError("El stock contado no puede ser negativo.")
        return self.validar_cantidad(valor)

    def validate(self, datos):
        por_bulto = self.leer_bultos(datos, minimo=Decimal("0"))  # se puede contar 0 cajones
        if por_bulto is not None:
            datos["stock_real"], detalle = por_bulto
            datos["motivo"] = f"{datos['motivo']} · se contaron {detalle}"[:200]
        elif datos.get("stock_real") is None:
            raise serializers.ValidationError({"stock_real": "Indicá cuánto hay en realidad."})
        return datos


class MovimientoSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source="producto.nombre")
    unidad = serializers.CharField(source="producto.unidad")
    seccion = serializers.CharField(source="producto.categoria.seccion.nombre")
    tipo_texto = serializers.CharField(source="get_tipo_display")
    usuario = serializers.CharField(source="usuario.nombre_completo")

    class Meta:
        model = MovimientoStock
        fields = [
            "id", "producto", "producto_nombre", "unidad", "seccion", "tipo", "tipo_texto", "cantidad",
            "stock_resultante", "costo_unitario", "valor", "motivo", "usuario", "turno", "fecha_hora",
        ]


def registrar_movimiento(producto_id, usuario, tipo, calcular):
    """Aplica un movimiento de stock de forma segura.

    Bloquea la fila del producto mientras dura la operación, para que dos personas cargando
    a la vez no pisen el stock. `calcular(producto)` devuelve (cantidad con signo, costo, motivo).
    """
    with transaction.atomic():
        producto = Producto.objects.select_for_update().select_related("categoria__seccion").get(pk=producto_id)
        cantidad, costo, motivo = calcular(producto)
        producto.stock_actual += cantidad
        producto.save(update_fields=["stock_actual"])
        MovimientoStock.objects.create(
            producto=producto, tipo=tipo, cantidad=cantidad, stock_resultante=producto.stock_actual,
            costo_unitario=producto.precio_costo if costo is None else costo,
            motivo=(motivo or "").strip()[:200] or None,
            usuario=usuario, turno=getattr(usuario, "turno_abierto", None),
        )
    return producto


class MovimientosViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """GET /api/movimientos/ — historial de stock. Filtros: ?producto=  ?tipo=  ?desde=  ?hasta= (AAAA-MM-DD)

    Dueños y encargados (incluye costos). Devuelve hasta 300, lo más nuevo primero.
    """

    serializer_class = MovimientoSerializer
    permission_classes = [EsEncargadoOAdministrador, PasswordAlDia]
    MAXIMO = 300

    def get_queryset(self):
        qs = MovimientoStock.objects.select_related("producto__categoria__seccion", "usuario")
        p = self.request.query_params
        if p.get("producto", "").isdigit():
            qs = qs.filter(producto_id=p["producto"])
        if p.get("tipo"):
            qs = qs.filter(tipo=p["tipo"])
        try:
            if p.get("desde"):
                qs = qs.filter(fecha_hora__gte=inicio_del_dia(date.fromisoformat(p["desde"])))
            if p.get("hasta"):
                qs = qs.filter(fecha_hora__lt=inicio_del_dia(date.fromisoformat(p["hasta"]) + timedelta(days=1)))
        except ValueError:
            raise serializers.ValidationError({"detail": "Las fechas deben tener el formato AAAA-MM-DD."})
        return qs[: self.MAXIMO]


def inicio_del_dia(fecha):
    return timezone.make_aware(datetime.combine(fecha, time.min))


class ProductosViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                       mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """
    GET   /api/productos/                   lista. Filtros: ?seccion=  ?categoria=  ?activo=1|0  ?q=texto
    POST  /api/productos/                   alta (dueños y encargados)
    GET   /api/productos/{id}/
    PATCH /api/productos/{id}/              corregir nombre, código, categoría o unidad (no precios)
    POST  /api/productos/{id}/desactivar/   baja {motivo?}
    POST  /api/productos/{id}/reactivar/
    """

    http_method_names = ["get", "post", "patch", "head", "options"]  # sin PUT: se edita solo lo que cambia

    def get_serializer_class(self):
        return ProductoEdicionSerializer if self.action == "partial_update" else ProductoSerializer

    @transaction.atomic
    def perform_update(self, serializer):
        antes = foto(serializer.instance)
        producto = serializer.save()
        detalle = serializer.describir_cambios(antes, foto(producto))
        if detalle:  # si no cambió nada, no se registra
            CambioProducto.objects.create(
                producto=producto, realizado_por=self.request.user, accion=CambioProducto.EDICION,
                detalle=detalle[:300],
            )

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return super().get_permissions()  # cualquiera con sesión
        return [EsEncargadoOAdministrador(), PasswordAlDia()]

    def get_queryset(self):
        qs = Producto.objects.select_related("categoria__seccion")
        p = self.request.query_params
        if p.get("seccion"):
            qs = qs.filter(categoria__seccion_id=p["seccion"])
        if p.get("categoria"):
            qs = qs.filter(categoria_id=p["categoria"])
        if p.get("activo") in ("0", "1"):
            qs = qs.filter(activo=p["activo"] == "1")
        if p.get("q"):
            texto = p["q"].strip()
            qs = qs.filter(Q(nombre__icontains=texto) | Q(codigo=texto) | Q(codigo_barras=texto))
        return qs

    @transaction.atomic
    def perform_create(self, serializer):
        producto = serializer.save(creado_por=self.request.user)
        CambioProducto.objects.create(
            producto=producto, realizado_por=self.request.user, accion=CambioProducto.ALTA,
            detalle=f"Venta ${producto.precio_venta} · Costo ${producto.precio_costo}",
        )

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def desactivar(self, request, pk=None):
        producto = self.get_object()
        if not producto.activo:
            return error("Este producto ya está dado de baja.")
        producto.activo = False
        producto.save(update_fields=["activo"])
        motivo = str(request.data.get("motivo", "")).strip()[:300] or None
        CambioProducto.objects.create(
            producto=producto, realizado_por=request.user, accion=CambioProducto.BAJA, detalle=motivo,
        )
        return Response(self.get_serializer(producto).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def reactivar(self, request, pk=None):
        producto = self.get_object()
        if producto.activo:
            return error("Este producto ya está activo.")
        producto.activo = True
        producto.save(update_fields=["activo"])
        CambioProducto.objects.create(
            producto=producto, realizado_por=request.user, accion=CambioProducto.REACTIVACION,
        )
        return Response(self.get_serializer(producto).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def precio(self, request, pk=None):
        """POST {precio_venta?, precio_costo?} — cambia el precio de un solo producto (RF-90)."""
        datos = PrecioSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        producto = Producto.objects.select_for_update().select_related("categoria__seccion").get(pk=self.get_object().pk)
        venta = datos.validated_data.get("precio_venta", producto.precio_venta)
        costo = datos.validated_data.get("precio_costo", producto.precio_costo)
        if not guardar_precios(producto, venta, costo, request.user, "cambio individual"):
            return error("El producto ya tiene esos precios: no hay nada que cambiar.")
        return Response(self.get_serializer(producto).data)

    # ----- Stock (RF-34 a RF-37). El stock solo cambia con estos movimientos (RN-09) -----

    def mover_stock(self, request, tipo, clase_serializer, calcular):
        producto = self.get_object()
        datos = clase_serializer(data=request.data, producto=producto)
        datos.is_valid(raise_exception=True)
        d = datos.validated_data
        with transaction.atomic():
            if tipo == MovimientoStock.INGRESO and producto.activo:
                # Si estaba como «suelto» y llegó en cajón, el producto recuerda en qué llega
                recordar_presentacion(producto, d.get("presentacion"), d.get("contenido"), request.user)
            producto = registrar_movimiento(producto.pk, request.user, tipo, lambda p: calcular(p, d))
        return Response(self.get_serializer(producto).data)

    @action(detail=True, methods=["post"])
    def ingreso(self, request, pk=None):
        """POST {cantidad} o {bultos, contenido?}, más costo_unitario? o costo_bulto?, motivo? — llegó mercadería."""

        def calcular(producto, d):
            if not producto.activo:
                raise serializers.ValidationError({"detail": "Este producto está dado de baja. Reactivalo para cargarle stock."})
            return d["cantidad"], d.get("costo_unitario"), d.get("motivo")

        return self.mover_stock(request, MovimientoStock.INGRESO, IngresoSerializer, calcular)

    @action(detail=True, methods=["post"])
    def perdida(self, request, pk=None):
        """POST {cantidad, motivo} — mercadería vencida, rota o en mal estado: resta del stock (RF-36)."""

        def calcular(producto, d):
            if d["cantidad"] > producto.stock_actual:
                raise serializers.ValidationError({"cantidad": [
                    f"En el sistema hay {texto_cantidad(producto.stock_actual)}. "
                    "Si en realidad hay otra cantidad, primero hacé un recuento."
                ]})
            return -d["cantidad"], None, d["motivo"]

        return self.mover_stock(request, MovimientoStock.PERDIDA, PerdidaSerializer, calcular)

    @action(detail=True, methods=["post"])
    def ajuste(self, request, pk=None):
        """POST {stock_real, motivo} — recuento: se contó la mercadería y no coincide con el sistema (RF-37)."""

        def calcular(producto, d):
            diferencia = d["stock_real"] - producto.stock_actual
            if diferencia == 0:
                raise serializers.ValidationError({"stock_real": ["El sistema ya tiene esa cantidad: no hay nada que ajustar."]})
            return diferencia, None, d["motivo"]

        return self.mover_stock(request, MovimientoStock.AJUSTE, AjusteSerializer, calcular)


# ---------- Precios (etapa 6, RF-90 a RF-94) ----------

CENTAVOS = Decimal("0.01")
REDONDEOS = (0, 1, 10, 50, 100)  # 0 = sin redondear; 10 = al múltiplo de $10 más cercano


class PrecioSerializer(serializers.Serializer):
    """Precio nuevo de un producto. Se puede mandar uno solo de los dos."""

    precio_venta = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=CENTAVOS, required=False,
        error_messages={"min_value": "El precio de venta tiene que ser mayor a 0."},
    )
    precio_costo = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0"), required=False,
        error_messages={"min_value": "El precio de costo no puede ser negativo."},
    )

    def validate(self, datos):
        if not datos:
            raise serializers.ValidationError({"precio_venta": "Escribí el precio nuevo."})
        return datos


class AjustePreciosSerializer(serializers.Serializer):
    """Aumento o rebaja por porcentaje a los productos de una categoría (ej.: +20 % a todo Pollo)."""

    categoria = serializers.PrimaryKeyRelatedField(
        queryset=Categoria.objects.select_related("seccion"),
        error_messages={"does_not_exist": "La categoría no existe.", "required": "Elegí una categoría."},
    )
    # Opcional: solo algunos productos de la categoría. Si falta, van todos los que están a la venta
    productos = serializers.ListField(child=serializers.IntegerField(), required=False)
    # Positivo sube, negativo baja
    porcentaje = serializers.DecimalField(
        max_digits=6, decimal_places=2,
        error_messages={"required": "Escribí el porcentaje.", "invalid": "Escribí el porcentaje con números."},
    )
    aplicar_a = serializers.ChoiceField(choices=["VENTA", "COSTO", "AMBOS"], default="VENTA")
    redondeo = serializers.IntegerField(default=0)
    confirmar = serializers.BooleanField(default=False)

    def validate_porcentaje(self, valor):
        if valor == 0:
            raise serializers.ValidationError("El porcentaje no puede ser 0.")
        if valor < -90:
            raise serializers.ValidationError("No se puede bajar más de un 90 %.")
        if valor > 500:
            raise serializers.ValidationError("No se puede subir más de un 500 % de una vez.")
        return valor

    def validate_redondeo(self, valor):
        if valor not in REDONDEOS:
            raise serializers.ValidationError("Elegí un redondeo de la lista.")
        return valor


def aplicar_porcentaje(valor, porcentaje, redondeo=0):
    """6500 con +20 % → 7800. Con redondeo 100, 7843 → 7800 (al múltiplo más cercano, nunca a 0)."""
    nuevo = valor * (Decimal(100) + porcentaje) / Decimal(100)
    if redondeo:
        paso = Decimal(redondeo)
        nuevo = (nuevo / paso).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * paso
        if nuevo <= 0:
            nuevo = paso
    return nuevo.quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def texto_porcentaje(porcentaje):
    """Decimal → «+20 %» o «−7,5 %»."""
    return f"{'+' if porcentaje > 0 else '−'}{texto_cantidad(abs(porcentaje))} %"


def guardar_precios(producto, venta, costo, usuario, origen):
    """Guarda los precios nuevos y deja el cambio en la auditoría. Devuelve False si no cambió nada."""
    cambios = []
    if venta != producto.precio_venta:
        cambios.append(f"Venta ${producto.precio_venta} → ${venta}")
    if costo != producto.precio_costo:
        cambios.append(f"Costo ${producto.precio_costo} → ${costo}")
    if not cambios:
        return False
    producto.precio_venta, producto.precio_costo = venta, costo
    producto.save(update_fields=["precio_venta", "precio_costo"])
    CambioProducto.objects.create(
        producto=producto, realizado_por=usuario, accion=CambioProducto.PRECIO,
        detalle=" · ".join(cambios + [origen])[:300],
    )
    return True


class PreciosViewSet(viewsets.ViewSet):
    """POST /api/precios/ajuste/ — sube o baja por porcentaje los precios de una categoría.

    Sin `confirmar` no guarda nada: devuelve cómo quedaría cada precio, para revisarlo antes.
    Las ventas ya hechas no cambian: cada recibo guarda el precio de su momento (RN-11).
    """

    permission_classes = [EsEncargadoOAdministrador, PasswordAlDia]

    @action(detail=False, methods=["post"])
    @transaction.atomic
    def ajuste(self, request):
        s = AjustePreciosSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        categoria, porcentaje, redondeo = d["categoria"], d["porcentaje"], d["redondeo"]
        cambia_venta = d["aplicar_a"] in ("VENTA", "AMBOS")
        cambia_costo = d["aplicar_a"] in ("COSTO", "AMBOS")

        de_la_categoria = Producto.objects.filter(categoria=categoria, activo=True)
        qs = de_la_categoria.order_by("nombre")
        if "productos" in d:
            qs = qs.filter(pk__in=d["productos"])
        if d["confirmar"]:
            qs = qs.select_for_update()
        productos = list(qs)
        if not productos:
            return error(
                "Elegí al menos un producto." if "productos" in d
                else "Esa categoría no tiene productos a la venta."
            )

        parcial = de_la_categoria.count() != len(productos)
        origen = f"{texto_porcentaje(porcentaje)} a {'productos de' if parcial else 'toda'} la categoría {categoria.nombre}"

        filas, cambiados = [], 0
        for p in productos:
            venta = aplicar_porcentaje(p.precio_venta, porcentaje, redondeo) if cambia_venta else p.precio_venta
            costo = aplicar_porcentaje(p.precio_costo, porcentaje) if cambia_costo else p.precio_costo
            venta = max(venta, CENTAVOS)
            filas.append({
                "id": p.id, "nombre": p.nombre, "unidad": p.unidad,
                "precio_venta": p.precio_venta, "precio_venta_nuevo": venta,
                "precio_costo": p.precio_costo, "precio_costo_nuevo": costo,
                "cambia": venta != p.precio_venta or costo != p.precio_costo,
                "bajo_costo": venta < costo,  # se avisa, pero se permite (RN-16)
            })
            if d["confirmar"]:
                cambiados += guardar_precios(p, venta, costo, request.user, origen)

        return Response({
            "categoria": {"id": categoria.id, "nombre": categoria.nombre, "seccion": categoria.seccion.nombre},
            "porcentaje": porcentaje, "aplicar_a": d["aplicar_a"], "redondeo": redondeo,
            "aplicado": d["confirmar"], "cambiados": cambiados, "productos": filas,
        })
