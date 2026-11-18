"""API de gastos: una lista del día donde cualquiera anota un monto y su propósito.

Anotar y ver la lista de hoy: cualquiera con sesión.
Ver otros días: dueños y encargados.
Anular: quien lo anotó (el mismo día), o un encargado o dueño. Los gastos no se borran.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core import dia
from productos.api import inicio_del_dia

from .models import Gasto

CENTAVOS = Decimal("0.01")
MAXIMO = 500


def error(mensaje, codigo=status.HTTP_400_BAD_REQUEST):
    return Response({"detail": str(mensaje)}, status=codigo)


def ve_todo(usuario):
    return usuario.es_administrador or usuario.es_encargado


def puede_anular(usuario, gasto):
    """Lo anula quien lo anotó, el mismo día; o un encargado o dueño."""
    if gasto.anulado:
        return False
    if ve_todo(usuario):
        return True
    return gasto.usuario_id == usuario.id and dia.fecha_local(gasto.fecha_hora) == dia.hoy()


class GastoSerializer(serializers.ModelSerializer):
    monto = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=CENTAVOS,
        error_messages={"min_value": "El monto tiene que ser mayor a 0.", "required": "Escribí el monto.",
                        "invalid": "Escribí el monto con números."},
    )
    proposito = serializers.CharField(
        max_length=200,
        error_messages={"blank": "Anotá para qué fue el gasto.", "required": "Anotá para qué fue el gasto."},
    )
    usuario = serializers.CharField(source="usuario.nombre_completo", read_only=True)
    anulado_por = serializers.SerializerMethodField()
    puede_anular = serializers.SerializerMethodField()

    class Meta:
        model = Gasto
        fields = ["id", "fecha_hora", "monto", "proposito", "usuario", "anulado", "anulado_por", "anulado_en",
                  "motivo_anulacion", "puede_anular"]
        read_only_fields = ["fecha_hora", "anulado", "anulado_en", "motivo_anulacion"]

    def validate_proposito(self, valor):
        valor = " ".join(valor.split())
        if len(valor) < 3:
            raise serializers.ValidationError("Anotá para qué fue el gasto.")
        return valor[0].upper() + valor[1:]

    def get_anulado_por(self, gasto):
        return gasto.anulado_por.nombre_completo if gasto.anulado_por else None

    def get_puede_anular(self, gasto):
        return puede_anular(self.context["request"].user, gasto)


class GastosViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    """
    GET  /api/gastos/?fecha=AAAA-MM-DD   la lista de un día (sin fecha, hoy) con su total. Otros días: dueños y encargados
    POST /api/gastos/                    anotar un gasto {monto, proposito} — cualquiera
    POST /api/gastos/{id}/anular/        {motivo?}
    """

    serializer_class = GastoSerializer
    queryset = Gasto.objects.select_related("usuario", "anulado_por")

    def list(self, request):
        hoy = dia.hoy()
        try:
            fecha = date.fromisoformat(request.query_params["fecha"]) if request.query_params.get("fecha") else hoy
        except ValueError:
            return error("La fecha debe tener el formato AAAA-MM-DD.")
        if fecha != hoy and not ve_todo(request.user):
            return error("Solo podés ver los gastos de hoy.", status.HTTP_403_FORBIDDEN)
        gastos = list(self.get_queryset().filter(
            fecha_hora__gte=inicio_del_dia(fecha), fecha_hora__lt=inicio_del_dia(fecha + timedelta(days=1)),
        )[:MAXIMO])
        vigentes = [g for g in gastos if not g.anulado]
        return Response({
            "fecha": fecha.isoformat(),
            "cantidad": len(vigentes),
            "total": str(sum((g.monto for g in vigentes), Decimal(0)).quantize(CENTAVOS)),
            "gastos": self.get_serializer(gastos, many=True).data,
        })

    def perform_create(self, serializer):
        usuario = self.request.user
        serializer.save(usuario=usuario, turno=getattr(usuario, "turno_abierto", None))

    @action(detail=True, methods=["post"])
    def anular(self, request, pk=None):
        with transaction.atomic():
            gasto = Gasto.objects.select_for_update().filter(pk=pk).first()
            if gasto is None:
                return error("El gasto no existe.", status.HTTP_404_NOT_FOUND)
            if gasto.anulado:
                return error("Este gasto ya estaba anulado.")
            if not puede_anular(request.user, gasto):
                return error("Solo podés anular los gastos que anotaste hoy. Pedile a un encargado.", status.HTTP_403_FORBIDDEN)
            gasto.anulado = True
            gasto.anulado_por = request.user
            gasto.anulado_en = timezone.now()
            gasto.motivo_anulacion = str(request.data.get("motivo") or "").strip()[:200] or None
            gasto.save(update_fields=["anulado", "anulado_por", "anulado_en", "motivo_anulacion"])
        return Response(self.get_serializer(self.get_queryset().get(pk=gasto.pk)).data)
