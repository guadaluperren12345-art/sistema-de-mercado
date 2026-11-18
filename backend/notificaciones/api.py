"""API de avisos a los dueños (RF-123 a RF-131). Todo es solo para administradores.

GET  /api/notificaciones/                      mis avisos (los últimos 40) y cuántos tengo sin leer
GET  /api/notificaciones/?solo=cuenta          solo cuántos tengo sin leer (para el encabezado)
POST /api/notificaciones/leer/   {id?}         marca uno como leído, o todos si no se manda `id`
GET  /api/notificaciones/configuracion/        cómo están configurados Telegram y el correo
PUT  /api/notificaciones/configuracion/        cambia el bot, la cuenta de correo o mi correo
POST /api/notificaciones/telegram/vincular/    busca mi mensaje al bot y guarda mi Telegram
POST /api/notificaciones/telegram/desvincular/
POST /api/notificaciones/probar/               me manda un aviso de prueba por los tres canales
"""

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.dia import TEXTO_HORA_DE_CIERRE
from usuarios.permisos import EsAdministrador, PasswordAlDia

from . import servicios
from .models import ConfiguracionNotificaciones, Envio, Notificacion

MAX_AVISOS = 40


def error(mensaje, codigo=status.HTTP_400_BAD_REQUEST):
    return Response({"detail": str(mensaje)}, status=codigo)


class VistaDeDueños(APIView):
    permission_classes = [EsAdministrador, PasswordAlDia]


def aviso_en_json(aviso):
    return {
        "id": aviso.id,
        "titulo": aviso.titulo,
        "texto": aviso.texto,
        "creada_en": aviso.creada_en,
        "leida": aviso.leida_en is not None,
        "fecha_cierre": aviso.cierre.fecha.isoformat() if aviso.cierre else None,
        "envios": [
            {"canal": e.canal, "nombre": e.get_canal_display(), "estado": e.estado,
             "estado_texto": e.get_estado_display(), "error": e.error}
            for e in aviso.envios.all()
        ],
    }


class NotificacionesView(VistaDeDueños):
    def get(self, request):
        mias = Notificacion.objects.filter(usuario=request.user)
        sin_leer = mias.filter(leida_en__isnull=True).count()
        if request.query_params.get("solo") == "cuenta":
            return Response({"sin_leer": sin_leer})
        avisos = mias.select_related("cierre").prefetch_related("envios")[:MAX_AVISOS]
        return Response({"sin_leer": sin_leer, "notificaciones": [aviso_en_json(a) for a in avisos]})


class LeerView(VistaDeDueños):
    def post(self, request):
        pendientes = Notificacion.objects.filter(usuario=request.user, leida_en__isnull=True)
        if request.data.get("id"):
            if not str(request.data["id"]).isdigit():
                return error("El aviso no es válido.")
            pendientes = pendientes.filter(pk=request.data["id"])
        pendientes.update(leida_en=timezone.now())
        return Response({"sin_leer": Notificacion.objects.filter(usuario=request.user, leida_en__isnull=True).count()})


def estado_de_configuracion(usuario):
    config = ConfiguracionNotificaciones.actual()
    vinculo = servicios.vinculo_de(usuario)
    dueños = []
    for d in servicios.dueños():
        canales = servicios.canales_de(d, config)
        dueños.append({"id": d.id, "nombre": d.nombre_completo,
                       "telegram": Envio.TELEGRAM in canales, "email": Envio.EMAIL in canales})
    return {
        "hora_cierre": TEXTO_HORA_DE_CIERRE,
        "telegram": {
            "configurado": config.telegram_listo,
            "bot": config.telegram_bot,
            "vinculado": vinculo.vinculado,
            "mi_nombre": vinculo.nombre,
            "codigo": vinculo.codigo,
            "enlace": f"https://t.me/{config.telegram_bot}?start={vinculo.codigo}" if config.telegram_bot else None,
        },
        "email": {
            "configurado": config.email_listo,
            "host": config.email_host,
            "puerto": config.email_puerto,
            "usuario": config.email_usuario,
            "mi_email": usuario.email or "",
        },
        "dueños": dueños,
    }


class ConfiguracionView(VistaDeDueños):
    def get(self, request):
        return Response(estado_de_configuracion(request.user))

    def put(self, request):
        """Solo cambia lo que se manda. El token y la contraseña se guardan pero nunca se devuelven."""
        d = request.data
        config = ConfiguracionNotificaciones.actual()
        cambio_config = False

        if "telegram_token" in d:
            token = str(d["telegram_token"] or "").strip()
            if token:
                try:
                    config.telegram_bot = servicios.verificar_bot(token)
                except servicios.ErrorDeEnvio as e:
                    return error(e)
            else:
                config.telegram_bot = ""
            config.telegram_token = token
            cambio_config = True

        if "email_usuario" in d:
            correo = str(d["email_usuario"] or "").strip()
            if correo:
                try:
                    validate_email(correo)
                except ValidationError:
                    return error("La cuenta de correo del mercado no es una dirección válida.")
            else:
                config.email_password = ""
            config.email_usuario = correo
            cambio_config = True
        if d.get("email_password"):
            # Las contraseñas de aplicación de Gmail se muestran con espacios: se guardan sin ellos
            config.email_password = str(d["email_password"]).replace(" ", "")[:100]
            cambio_config = True
        if d.get("email_host"):
            config.email_host = str(d["email_host"]).strip()[:100]
            cambio_config = True
        if d.get("email_puerto"):
            if not str(d["email_puerto"]).isdigit() or not 0 < int(d["email_puerto"]) < 65536:
                return error("El puerto del correo no es válido.")
            config.email_puerto = int(d["email_puerto"])
            cambio_config = True

        if "mi_email" in d:
            correo = str(d["mi_email"] or "").strip()
            if correo:
                try:
                    validate_email(correo)
                except ValidationError:
                    return error("Tu correo no es una dirección válida.")
            request.user.email = correo or None
            request.user.save(update_fields=["email"])

        if cambio_config:
            config.actualizado_por, config.actualizado_en = request.user, timezone.now()
            config.save()
        return Response(estado_de_configuracion(request.user))


class VincularTelegramView(VistaDeDueños):
    def post(self, request):
        try:
            encontrado = servicios.vincular_telegram(request.user)
        except servicios.ErrorDeEnvio as e:
            return error(e)
        if not encontrado:
            return error("Todavía no llegó tu mensaje al bot. Abrí el enlace, tocá «Iniciar» en Telegram y probá de nuevo.")
        return Response(estado_de_configuracion(request.user))


class DesvincularTelegramView(VistaDeDueños):
    def post(self, request):
        servicios.desvincular_telegram(request.user)
        return Response(estado_de_configuracion(request.user))


class ProbarView(VistaDeDueños):
    def post(self, request):
        return Response({"resultados": servicios.probar(request.user)})
