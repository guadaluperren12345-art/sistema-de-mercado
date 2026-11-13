"""API de clientes y cuenta corriente («fiado»).

Ver clientes y su cuenta, y cobrar un pago: cualquiera con sesión (el cajero cobra la deuda).
Alta, corrección y baja de clientes: los dueños y los encargados que un dueño autorizó.
Límites de fiado (el general y el de cada cliente) y ajustes de la cuenta: solo los dueños.
"""

import re
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from usuarios.permisos import EsAdministrador, GestionaClientes, PasswordAlDia

from . import servicios
from .models import CambioCliente, Cliente, ConfiguracionCuentas, MovimientoCuenta

CENTAVOS = Decimal("0.01")
MEDIOS_DE_PAGO = [
    ("EFECTIVO", "Efectivo"),
    ("DEBITO", "Tarjeta de débito"),
    ("CREDITO", "Tarjeta de crédito"),
    ("TRANSFERENCIA", "Transferencia"),
    ("QR", "QR / billetera virtual"),
]
NOMBRE_MEDIO = dict(MEDIOS_DE_PAGO)
MAX_MOVIMIENTOS = 200


def error(mensaje, codigo=status.HTTP_400_BAD_REQUEST):
    return Response({"detail": str(mensaje)}, status=codigo)


def texto_limite(valor):
    return "sin límite" if valor is None else servicios.pesos(valor)


# ---------- Serializers ----------

class ClienteSerializer(serializers.ModelSerializer):
    limite = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0"), required=False, allow_null=True,
        error_messages={"min_value": "El límite no puede ser negativo."},
    )
    # El tope que le corresponde hoy (el propio o el general) y cuánto le queda para fiar. null = sin tope
    limite_vigente = serializers.SerializerMethodField()
    disponible = serializers.SerializerMethodField()

    class Meta:
        model = Cliente
        fields = [
            "id", "nombre", "dni", "telefono", "direccion", "nota", "limite", "limite_vigente", "disponible",
            "saldo", "activo", "fecha_creacion",
        ]
        read_only_fields = ["saldo", "activo", "fecha_creacion"]
        extra_kwargs = {
            "nombre": {"validators": []},  # la unicidad se valida abajo con un mensaje claro
            **{campo: {"required": False, "allow_null": True, "allow_blank": True}
               for campo in ("dni", "telefono", "direccion", "nota")},
        }

    def get_limite_vigente(self, cliente):
        limite = servicios.limite_de(cliente, self.context["configuracion"])
        return None if limite is None else str(limite)

    def get_disponible(self, cliente):
        limite = servicios.limite_de(cliente, self.context["configuracion"])
        return None if limite is None else str(max(limite - cliente.saldo, Decimal(0)))

    def otros(self):
        qs = Cliente.objects.all()
        return qs.exclude(pk=self.instance.pk) if self.instance else qs

    def validate_nombre(self, valor):
        valor = " ".join(valor.split())
        if len(valor) < 3:
            raise serializers.ValidationError("Escribí el nombre y apellido del cliente.")
        valor = valor[0].upper() + valor[1:]
        # La base no distingue mayúsculas ni acentos: «Juan Perez» = «juan pérez»
        existente = self.otros().filter(nombre=valor).first()
        if existente:
            estado = " Está dado de baja: podés reactivarlo." if not existente.activo else ""
            raise serializers.ValidationError(
                f"Ya hay un cliente con ese nombre.{estado} Si es otra persona, agregale algo para "
                "distinguirla (ej.: «Juan Pérez (kiosco)»)."
            )
        return valor

    def validate_dni(self, valor):
        valor = re.sub(r"[.\s-]", "", valor or "")
        if not valor:
            return None
        if not re.fullmatch(r"\d{7,11}", valor):
            raise serializers.ValidationError("El DNI o CUIT debe tener entre 7 y 11 números.")
        existente = self.otros().filter(dni=valor).first()
        if existente:
            raise serializers.ValidationError(f"Ese DNI ya lo tiene «{existente.nombre}».")
        return valor

    def limpiar(self, valor):
        return " ".join((valor or "").split()) or None

    def validate_telefono(self, valor):
        return self.limpiar(valor)

    def validate_direccion(self, valor):
        return self.limpiar(valor)

    def validate_nota(self, valor):
        return self.limpiar(valor)

    def validate(self, datos):
        # El límite propio de un cliente lo decide un dueño (RF-100)
        if "limite" in datos and not self.context["request"].user.es_administrador:
            actual = self.instance.limite if self.instance else None
            if datos["limite"] != actual:
                raise serializers.ValidationError({"limite": "El límite de fiado lo fijan solo los dueños."})
        return datos

    CAMPOS = {"nombre": "Nombre", "dni": "DNI", "telefono": "Teléfono", "direccion": "Dirección", "nota": "Nota"}


class MovimientoSerializer(serializers.ModelSerializer):
    numero = serializers.CharField()
    tipo_texto = serializers.CharField(source="get_tipo_display")
    cliente_nombre = serializers.CharField(source="cliente.nombre")
    usuario = serializers.CharField(source="usuario.nombre_completo")
    medio_pago_texto = serializers.SerializerMethodField()
    venta_numero = serializers.SerializerMethodField()

    class Meta:
        model = MovimientoCuenta
        fields = [
            "id", "numero", "cliente", "cliente_nombre", "tipo", "tipo_texto", "importe", "saldo_resultante",
            "venta", "venta_numero", "medio_pago", "medio_pago_texto", "detalle", "usuario", "fecha_hora",
        ]

    def get_medio_pago_texto(self, m):
        return NOMBRE_MEDIO.get(m.medio_pago)

    def get_venta_numero(self, m):
        return f"{m.venta_id:06d}" if m.venta_id else None


class PagoSerializer(serializers.Serializer):
    importe = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=CENTAVOS,
        error_messages={"min_value": "El importe tiene que ser mayor a 0.", "required": "Escribí cuánto paga.",
                        "invalid": "Escribí el importe con números."},
    )
    medio_pago = serializers.ChoiceField(
        choices=MEDIOS_DE_PAGO, error_messages={"invalid_choice": "Elegí cómo paga el cliente.",
                                                "required": "Elegí cómo paga el cliente."}
    )
    detalle = serializers.CharField(max_length=200, required=False, allow_blank=True)


class AjusteSerializer(serializers.Serializer):
    # Positivo: suma deuda (por ejemplo, lo que debía en el cuaderno). Negativo: se la baja.
    importe = serializers.DecimalField(
        max_digits=14, decimal_places=2,
        error_messages={"required": "Escribí el importe.", "invalid": "Escribí el importe con números."},
    )
    motivo = serializers.CharField(
        max_length=200, error_messages={"blank": "Indicá el motivo del ajuste.", "required": "Indicá el motivo del ajuste."}
    )

    def validate_importe(self, valor):
        if valor == 0:
            raise serializers.ValidationError("El importe no puede ser 0.")
        return valor


# ---------- Vistas ----------

def foto(cliente):
    return {campo: getattr(cliente, campo) for campo in ClienteSerializer.CAMPOS}


class ClientesViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                      mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """
    GET   /api/clientes/                    lista. Filtros: ?activo=1|0  ?q=nombre o DNI  ?deben=1
    POST  /api/clientes/                    alta (dueños y encargados autorizados)
    GET   /api/clientes/{id}/
    PATCH /api/clientes/{id}/               corregir datos; `limite` solo los dueños (null = usa el general)
    POST  /api/clientes/{id}/desactivar/    baja {motivo?}
    POST  /api/clientes/{id}/reactivar/
    GET   /api/clientes/{id}/movimientos/   su cuenta, lo más nuevo primero (hasta 200)
    POST  /api/clientes/{id}/pago/          cobrar un pago {importe, medio_pago, detalle?} — cualquier cajero
    POST  /api/clientes/{id}/ajuste/        {importe con signo, motivo} — solo dueños
    """

    serializer_class = ClienteSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_permissions(self):
        if self.action in ("list", "retrieve", "movimientos", "pago"):
            return super().get_permissions()  # cualquiera con sesión
        if self.action == "ajuste":
            return [EsAdministrador(), PasswordAlDia()]
        return [GestionaClientes(), PasswordAlDia()]

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "configuracion": ConfiguracionCuentas.actual()}

    def get_queryset(self):
        qs = Cliente.objects.all()
        if self.action != "list":
            return qs
        p = self.request.query_params
        if p.get("activo") in ("0", "1"):
            qs = qs.filter(activo=p["activo"] == "1")
        if p.get("deben") == "1":
            qs = qs.filter(saldo__gt=0)
        if p.get("q"):
            texto = p["q"].strip()
            qs = qs.filter(Q(nombre__icontains=texto) | Q(dni=texto))
        return qs

    def responder(self, cliente, codigo=status.HTTP_200_OK, **extra):
        return Response({**self.get_serializer(cliente).data, **extra}, status=codigo)

    @transaction.atomic
    def perform_create(self, serializer):
        cliente = serializer.save(creado_por=self.request.user)
        detalle = f"Límite propio: {servicios.pesos(cliente.limite)}" if cliente.limite is not None else None
        CambioCliente.objects.create(
            cliente=cliente, realizado_por=self.request.user, accion=CambioCliente.ALTA, detalle=detalle,
        )

    @transaction.atomic
    def perform_update(self, serializer):
        antes, limite_antes = foto(serializer.instance), serializer.instance.limite
        cliente = serializer.save()
        despues = foto(cliente)
        cambios = [f"{titulo}: {antes[campo] or '—'} → {despues[campo] or '—'}"
                   for campo, titulo in ClienteSerializer.CAMPOS.items() if antes[campo] != despues[campo]]
        if cambios:
            CambioCliente.objects.create(
                cliente=cliente, realizado_por=self.request.user, accion=CambioCliente.EDICION,
                detalle=" · ".join(cambios)[:300],
            )
        if cliente.limite != limite_antes:
            general = "usa el general" if cliente.limite is None else servicios.pesos(cliente.limite)
            anterior = "usaba el general" if limite_antes is None else servicios.pesos(limite_antes)
            CambioCliente.objects.create(
                cliente=cliente, realizado_por=self.request.user, accion=CambioCliente.LIMITE,
                detalle=f"{anterior} → {general}",
            )

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def desactivar(self, request, pk=None):
        cliente = self.get_object()
        if not cliente.activo:
            return error("Este cliente ya está dado de baja.")
        cliente.activo = False
        cliente.save(update_fields=["activo"])
        motivo = str(request.data.get("motivo", "")).strip()[:300] or None
        CambioCliente.objects.create(
            cliente=cliente, realizado_por=request.user, accion=CambioCliente.BAJA, detalle=motivo,
        )
        return self.responder(cliente)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def reactivar(self, request, pk=None):
        cliente = self.get_object()
        if cliente.activo:
            return error("Este cliente ya está activo.")
        cliente.activo = True
        cliente.save(update_fields=["activo"])
        CambioCliente.objects.create(cliente=cliente, realizado_por=request.user, accion=CambioCliente.REACTIVACION)
        return self.responder(cliente)

    @action(detail=True, methods=["get"])
    def movimientos(self, request, pk=None):
        cliente = self.get_object()
        qs = cliente.movimientos.select_related("cliente", "usuario")[:MAX_MOVIMIENTOS]
        return Response(MovimientoSerializer(qs, many=True).data)

    @action(detail=True, methods=["post"])
    def pago(self, request, pk=None):
        """El cliente paga toda su deuda o una parte (RF-101). Devuelve el comprobante."""
        datos = PagoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        d = datos.validated_data
        with transaction.atomic():
            cliente = servicios.bloquear(self.get_object().pk)
            if cliente.saldo <= 0:
                return error(f"«{cliente.nombre}» no debe nada.")
            if d["importe"] > cliente.saldo:
                return error(f"«{cliente.nombre}» debe {servicios.pesos(cliente.saldo)}: no se puede cobrar más que eso.")
            movimiento = servicios.registrar(
                cliente, MovimientoCuenta.PAGO, -d["importe"], request.user,
                medio_pago=d["medio_pago"], detalle=d.get("detalle"),
            )
        return self.responder(cliente, status.HTTP_201_CREATED, comprobante=MovimientoSerializer(movimiento).data)

    @action(detail=True, methods=["post"])
    def ajuste(self, request, pk=None):
        """Un dueño corrige la cuenta a mano: deuda que venía del cuaderno, un pago mal cargado, etc. (RF-103)."""
        datos = AjusteSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        d = datos.validated_data
        with transaction.atomic():
            cliente = servicios.bloquear(self.get_object().pk)
            movimiento = servicios.registrar(
                cliente, MovimientoCuenta.AJUSTE, d["importe"], request.user, detalle=d["motivo"],
            )
        return self.responder(cliente, status.HTTP_201_CREATED, comprobante=MovimientoSerializer(movimiento).data)


class ConfiguracionView(APIView):
    """GET  /api/cuentas/configuracion/  — límite general de fiado y total que deben los clientes (con sesión)
    POST /api/cuentas/configuracion/  {limite_general: número o null} — solo dueños
    """

    def get_permissions(self):
        if self.request.method == "POST":
            return [EsAdministrador(), PasswordAlDia()]
        return super().get_permissions()

    def respuesta(self, configuracion):
        limite = configuracion.limite_general
        return Response({"limite_general": None if limite is None else str(limite)})

    def get(self, request):
        return self.respuesta(ConfiguracionCuentas.actual())

    @transaction.atomic
    def post(self, request):
        valor = request.data.get("limite_general")
        if valor in ("", None):
            nuevo = None
        else:
            campo = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0"))
            try:
                nuevo = campo.run_validation(valor)
            except serializers.ValidationError:
                return error("Escribí el límite con números, sin signo. Dejalo vacío para que no haya límite general.")
        configuracion = ConfiguracionCuentas.objects.select_for_update().get(pk=ConfiguracionCuentas.actual().pk)
        if nuevo != configuracion.limite_general:
            CambioCliente.objects.create(
                realizado_por=request.user, accion=CambioCliente.LIMITE_GENERAL,
                detalle=f"{texto_limite(configuracion.limite_general)} → {texto_limite(nuevo)}",
            )
            configuracion.limite_general = nuevo
            configuracion.save(update_fields=["limite_general"])
        return self.respuesta(configuracion)
