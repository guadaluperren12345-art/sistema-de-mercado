"""API de horarios, actividad, resumen y cierres del día. Todo es solo para los dueños (administradores)."""

from datetime import date, timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from usuarios.permisos import EsAdministrador, PasswordAlDia

from . import servicios
from .models import CierreDiario, Turno

MAX_DIAS = 92  # un período consultado no puede pasar de 3 meses


def error(mensaje):
    return Response({"detail": mensaje}, status=status.HTTP_400_BAD_REQUEST)


class ParametroInvalido(Exception):
    pass


def leer_fechas(params):
    """Lee ?desde=AAAA-MM-DD&hasta=AAAA-MM-DD. Sin parámetros, es el día de hoy."""
    hoy = timezone.localdate()
    try:
        desde = date.fromisoformat(params["desde"]) if params.get("desde") else hoy
        hasta = date.fromisoformat(params["hasta"]) if params.get("hasta") else desde
    except ValueError:
        raise ParametroInvalido("Las fechas deben tener el formato AAAA-MM-DD.")
    if hasta < desde:
        raise ParametroInvalido("La fecha «hasta» no puede ser anterior a «desde».")
    if (hasta - desde).days >= MAX_DIAS:
        raise ParametroInvalido("El período no puede ser de más de 3 meses.")
    return desde, hasta


def leer_momento(texto):
    momento = parse_datetime(texto or "")
    if momento is None:
        raise ParametroInvalido("La fecha y hora no son válidas.")
    return timezone.make_aware(momento) if timezone.is_naive(momento) else momento


class VistaDeDueños(APIView):
    """Base: solo administradores. Convierte los parámetros mal escritos en un error 400 claro."""

    permission_classes = [EsAdministrador, PasswordAlDia]

    def handle_exception(self, exc):
        if isinstance(exc, ParametroInvalido):
            return error(str(exc))
        return super().handle_exception(exc)


class TurnoSerializer(serializers.ModelSerializer):
    usuario = serializers.SerializerMethodField()
    corregido_por = serializers.SerializerMethodField()
    tipo_cierre_texto = serializers.CharField(source="get_tipo_cierre_display")

    class Meta:
        model = Turno
        fields = [
            "id", "usuario", "inicio", "fin", "abierto", "minutos", "ultima_actividad",
            "tipo_cierre", "tipo_cierre_texto", "para_revisar",
            "fin_original", "corregido_por", "corregido_en", "nota",
        ]

    def get_usuario(self, turno):
        u = turno.usuario
        return {"id": u.id, "nombre": u.nombre_completo, "rol": u.rol.nombre}

    def get_corregido_por(self, turno):
        return turno.corregido_por.nombre_completo if turno.corregido_por else None


class TurnosView(VistaDeDueños):
    """GET /api/turnos/?desde=&hasta=&usuario=  — turnos que empezaron en el período (RF-26).

    Otros filtros:  ?estado=abiertos (quién está trabajando ahora, RF-28)
                    ?estado=revisar  (los que cerró el sistema a las 00:00 y falta revisar, RF-27)
    """

    def get(self, request):
        servicios.cerrar_dias_pendientes()
        qs = Turno.objects.select_related("usuario__rol", "corregido_por")
        p = request.query_params
        if p.get("estado") == "abiertos":
            qs = qs.filter(fin__isnull=True)
        elif p.get("estado") == "revisar":
            qs = qs.filter(para_revisar=True)
        else:
            desde, hasta = leer_fechas(p)
            inicio, fin = servicios.rango_de_fechas(desde, hasta)
            qs = qs.filter(inicio__gte=inicio, inicio__lt=fin)
        if p.get("usuario"):
            qs = qs.filter(usuario_id=p["usuario"])
        return Response(TurnoSerializer(qs, many=True).data)


class CorregirTurnoView(VistaDeDueños):
    """POST /api/turnos/{id}/corregir/  {fin?, nota?}

    Con `fin`: corrige la hora de salida (o cierra un turno que quedó abierto).
    Sin `fin`: confirma que la hora que puso el sistema está bien.
    Siempre queda registrado quién lo hizo y la hora que había antes.
    """

    def post(self, request, pk):
        turno = Turno.objects.select_related("usuario__rol", "corregido_por").filter(pk=pk).first()
        if turno is None:
            return Response({"detail": "El turno no existe."}, status=status.HTTP_404_NOT_FOUND)

        ahora = timezone.now()
        nota = str(request.data.get("nota") or "").strip()[:300] or None

        if request.data.get("fin"):
            fin = leer_momento(request.data["fin"]).replace(second=0, microsecond=0)
            medianoche = servicios.inicio_del_dia(servicios.fecha_local(turno.inicio) + timedelta(days=1))
            if fin <= turno.inicio:
                return error("La hora de salida tiene que ser posterior a la de entrada.")
            if fin > medianoche:
                return error("La salida no puede pasar de las 00:00: después de esa hora empieza otro día.")
            if fin > ahora:
                return error("La hora de salida no puede estar en el futuro.")
            if turno.fin and turno.fin_original is None:
                turno.fin_original = turno.fin
            if turno.abierto:
                turno.tipo_cierre = Turno.ADMINISTRADOR
            turno.fin = fin
        elif turno.abierto:
            return error("Este turno sigue abierto. Indicá la hora de salida para cerrarlo.")

        turno.para_revisar = False
        turno.corregido_por = request.user
        turno.corregido_en = ahora
        turno.nota = nota
        turno.save()
        return Response(TurnoSerializer(turno).data)


class ActividadView(VistaDeDueños):
    """GET /api/actividad/?desde=&hasta=&usuario=&grupo=

    `desde` y `hasta` son fecha y hora (ISO). Devuelve todo lo que pasó en ese rato
    y quién tenía el sistema abierto.
    """

    def get(self, request):
        p = request.query_params
        desde, hasta = leer_momento(p.get("desde")), leer_momento(p.get("hasta"))
        if hasta <= desde:
            raise ParametroInvalido("La hora «hasta» tiene que ser posterior a «desde».")
        if hasta - desde > timedelta(days=MAX_DIAS):
            raise ParametroInvalido("El período no puede ser de más de 3 meses.")
        grupo = p.get("grupo") or None
        if grupo and grupo not in servicios.GRUPOS:
            raise ParametroInvalido("El tipo de actividad no existe.")
        usuario = p.get("usuario") or None
        if usuario and not usuario.isdigit():
            raise ParametroInvalido("El usuario no es válido.")
        return Response(servicios.actividad(desde, hasta, usuario_id=usuario, grupo=grupo))


class ResumenView(VistaDeDueños):
    """GET /api/resumen/?desde=AAAA-MM-DD&hasta=AAAA-MM-DD — entradas, salidas y horas del período."""

    def get(self, request):
        servicios.cerrar_dias_pendientes()
        desde, hasta = leer_fechas(request.query_params)
        return Response(servicios.resumen(desde, hasta))


class ResultadosView(VistaDeDueños):
    """GET /api/resultados/?desde=AAAA-MM-DD&hasta=AAAA-MM-DD — ganancia o pérdida de cada sección (hasta un año)."""

    def get(self, request):
        hoy = timezone.localdate()
        p = request.query_params
        try:
            desde = date.fromisoformat(p["desde"]) if p.get("desde") else hoy
            hasta = date.fromisoformat(p["hasta"]) if p.get("hasta") else desde
        except ValueError:
            raise ParametroInvalido("Las fechas deben tener el formato AAAA-MM-DD.")
        if hasta < desde:
            raise ParametroInvalido("La fecha «hasta» no puede ser anterior a «desde».")
        if (hasta - desde).days > 366:
            raise ParametroInvalido("El período no puede ser de más de un año.")
        return Response(servicios.resultados(desde, hasta))


class CierreDiarioSerializer(serializers.ModelSerializer):
    entro = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    resultado_dia = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    efectivo_esperado = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = CierreDiario
        fields = [
            "id", "fecha", "generado_en", "turnos", "minutos_trabajados", "turnos_cerrados_por_sistema",
            "movimientos_stock", "valor_ingresado", "valor_perdidas", "valor_ajustes", "cambios",
            "ventas_cantidad", "ventas_total", "ventas_efectivo", "ganancia_bruta",
            "ventas_fiado", "cobros_cuenta", "cobros_cuenta_efectivo",
            "gastos_cantidad", "gastos_total", "entro", "resultado_dia", "efectivo_esperado",
            "compras_total", "pagos_comerciantes", "pagos_comerciantes_efectivo",
        ]


class CierresView(VistaDeDueños):
    """GET /api/cierres/ — los últimos cierres automáticos del día (hasta 60)."""

    def get(self, request):
        servicios.cerrar_dias_pendientes()
        return Response(CierreDiarioSerializer(CierreDiario.objects.all()[:60], many=True).data)
