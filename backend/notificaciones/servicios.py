"""Avisos a los dueños: armar el texto de la caja del día y mandarlo por cada canal.

- Dentro del sistema: siempre (queda en la pantalla «Avisos»).
- Telegram: si está cargado el bot del mercado y el dueño vinculó su Telegram.
- Correo: si está cargada la cuenta de envío y el dueño tiene su correo anotado.

Los envíos de afuera necesitan internet. Si falla uno, queda pendiente y el planificador
(contenedor `tareas`) lo reintenta solo durante varias horas.
"""

import json
import logging
import secrets
import smtplib
import urllib.error
import urllib.request
from datetime import timedelta
from decimal import Decimal

from django.core.mail import EmailMessage, get_connection
from django.utils import timezone

from core.dia import TEXTO_HORA_DE_CIERRE
from usuarios.models import Rol, Usuario

from .models import ConfiguracionNotificaciones, Envio, Notificacion, VinculoTelegram

registro = logging.getLogger(__name__)

MAX_INTENTOS = 30  # con esperas de hasta 30 minutos: se insiste unas 13 horas
MAX_POR_VUELTA = 20
MAX_TELEGRAM = 4000  # Telegram no acepta mensajes de más de 4096 caracteres
MAX_GASTOS_EN_EL_AVISO = 15
SEGUNDOS_DE_ESPERA = 15

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


class ErrorDeEnvio(Exception):
    """No se pudo mandar el aviso. El mensaje se le puede mostrar al dueño (no lleva contraseñas)."""


def dueños():
    return Usuario.objects.filter(activo=True, rol__nombre=Rol.ADMINISTRADOR).select_related("rol").order_by("id")


# ---------- El texto de la caja del día ----------

def pesos(valor):
    """1234.5 -> "$1.234,50" (formato de Argentina)."""
    n = Decimal(valor).quantize(Decimal("0.01"))
    entero, decimales = f"{abs(n):,.2f}".split(".")
    return f"{'−' if n < 0 else ''}${entero.replace(',', '.')},{decimales}"


def _duracion(minutos):
    horas, resto = divmod(minutos, 60)
    return f"{horas} h {resto:02d} min" if horas else f"{resto} min"


def _hora(momento):
    return timezone.localtime(momento).strftime("%H:%M")


def texto_de_caja(cierre, r):
    """Título y texto del aviso con toda la caja de un día. `r` es el resumen de ese día."""
    fecha = cierre.fecha
    ventas, cuentas, gastos, compras, caja = r["ventas"], r["cuenta_corriente"], r["gastos"], r["comerciantes"], r["caja"]
    titulo = f"Caja del día {DIAS[fecha.weekday()]} {fecha:%d/%m/%Y}"
    lineas = [
        titulo.upper(),
        f"La hizo el sistema solo, a las {TEXTO_HORA_DE_CIERRE}.",
        "",
        f"RESULTADO DEL DÍA: {pesos(caja['resultado'])}",
        "(la plata que entró, menos los gastos y lo pagado a comerciantes)",
        "",
        f"PLATA QUE ENTRÓ: {pesos(caja['entro'])}",
        f"• Ventas: {pesos(ventas['total'])} en {ventas['cantidad']} {'venta' if ventas['cantidad'] == 1 else 'ventas'}",
    ]
    for m in ventas["por_medio"]:
        lineas.append(f"   – {m['nombre']}: {pesos(m['total'])} ({m['cantidad']})")
    if Decimal(ventas["fiado"]):
        lineas.append(f"• Vendido fiado (todavía no entró): −{pesos(ventas['fiado'])}")
    if cuentas["cobros"]:
        lineas.append(f"• Pagos de cuentas corrientes: +{pesos(cuentas['total'])} ({cuentas['cobros']})")
        for m in cuentas["por_medio"]:
            lineas.append(f"   – {m['nombre']}: {pesos(m['total'])} ({m['cantidad']})")
    if ventas["anuladas"] or ventas["modificadas"]:
        lineas.append(f"• Ventas anuladas: {ventas['anuladas']} · modificadas: {ventas['modificadas']}")

    lineas += ["", f"PLATA QUE SALIÓ: {pesos(Decimal(caja['gastos']) + Decimal(caja['pagos_comerciantes']))}"]
    lineas.append(f"• Gastos: {pesos(gastos['total'])} ({gastos['cantidad']})")
    for g in gastos["lista"][:MAX_GASTOS_EN_EL_AVISO]:
        lineas.append(f"   – {pesos(g['monto'])} · {g['proposito']} ({g['usuario']})")
    if gastos["cantidad"] > MAX_GASTOS_EN_EL_AVISO:
        lineas.append(f"   – … y {gastos['cantidad'] - MAX_GASTOS_EN_EL_AVISO} más (están en el sistema)")
    lineas.append(f"• Pagos a comerciantes: {pesos(compras['pagado'])} ({compras['pagos']})")

    lineas += ["", f"EFECTIVO QUE DEBERÍA HABER EN LA CAJA: {pesos(caja['efectivo'])}",
               "(ventas y pagos en efectivo, menos gastos y pagos en efectivo a comerciantes)"]

    if ventas["por_seccion"]:
        lineas += ["", "POR SECCIÓN"]
        for s in ventas["por_seccion"]:
            lineas.append(f"• {s['seccion']}: vendió {pesos(s['total'])} · ganancia {pesos(s['ganancia_bruta'])}")
    lineas.append(f"Ganancia bruta (lo vendido menos lo que costó esa mercadería): {pesos(ventas['ganancia_bruta'])}")

    mercaderia = r["mercaderia"]
    lineas += [
        "",
        "MERCADERÍA Y COMERCIANTES",
        f"• Mercadería que ingresó: {pesos(mercaderia['ingresos']['valor'])}",
        f"• Pérdidas: {pesos(mercaderia['perdidas']['valor'])}",
        f"• Compras a comerciantes: {pesos(compras['comprado'])} ({compras['compras']})",
        f"• Se les debe en total: {pesos(compras['deuda_actual'])}",
    ]

    personal = r["personal"]
    if personal["por_persona"]:
        lineas += ["", "PERSONAL"]
        for p in personal["por_persona"]:
            lineas.append(f"• {p['nombre']}: {_duracion(p['minutos'])}")
    for a in personal.get("abiertos", []):
        lineas.append(f"⚠ {a['nombre']} todavía no cerró su cuenta "
                      f"(entró {_hora(a['inicio'])}, último movimiento {_hora(a['ultima_actividad'])})")

    if not r["cambios"] and not personal["turnos"]:
        lineas += ["", "Ese día no hubo movimientos en el sistema."]
    return titulo, "\n".join(lineas)


# ---------- Crear los avisos ----------

def vinculo_de(usuario):
    """El vínculo de Telegram de un dueño; se crea con su código la primera vez."""
    vinculo, _ = VinculoTelegram.objects.get_or_create(usuario=usuario, defaults={"codigo": secrets.token_hex(5)})
    return vinculo


def canales_de(usuario, config):
    """Por dónde se le puede avisar a este dueño ahora mismo: {canal: destino}."""
    canales = {}
    if config.telegram_listo:
        chat = VinculoTelegram.objects.filter(usuario=usuario).values_list("chat_id", flat=True).first()
        if chat:
            canales[Envio.TELEGRAM] = chat
    if config.email_listo and usuario.email:
        canales[Envio.EMAIL] = usuario.email
    return canales


def crear_aviso(usuario, titulo, texto, cierre=None, config=None):
    """Deja el aviso en el sistema y encola los envíos por Telegram y correo."""
    config = config or ConfiguracionNotificaciones.actual()
    aviso = Notificacion.objects.create(usuario=usuario, cierre=cierre, titulo=titulo, texto=texto)
    for canal, destino in canales_de(usuario, config).items():
        Envio.objects.create(notificacion=aviso, canal=canal, destino=destino)
    return aviso


def avisar_cierre(cierre, r):
    """Le avisa a cada dueño que la caja del día está hecha. Un fallo acá nunca frena el cierre."""
    try:
        titulo, texto = texto_de_caja(cierre, r)
        config = ConfiguracionNotificaciones.actual()
        return [crear_aviso(u, titulo, texto, cierre, config) for u in dueños()]
    except Exception:  # noqa: BLE001 - la caja ya quedó guardada; el aviso se puede ver en el sistema
        registro.exception("No se pudo crear el aviso del cierre %s", cierre.fecha)
        return []


# ---------- Mandar por Telegram y por correo ----------

def _telegram(token, metodo, datos=None):
    """Llama a la API de Telegram. Los errores nunca incluyen el token."""
    pedido = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{metodo}",
        data=json.dumps(datos or {}).encode(), headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(pedido, timeout=SEGUNDOS_DE_ESPERA) as respuesta:
            cuerpo = json.load(respuesta)
    except urllib.error.HTTPError as e:
        if e.code in (401, 404):
            raise ErrorDeEnvio("El token del bot de Telegram no es válido.") from None
        try:
            descripcion = json.load(e).get("description", "")
        except Exception:  # noqa: BLE001
            descripcion = ""
        raise ErrorDeEnvio(f"Telegram rechazó el pedido: {descripcion or e.code}"[:300]) from None
    except (urllib.error.URLError, OSError, ValueError):
        raise ErrorDeEnvio("No se pudo conectar con Telegram. ¿La computadora del mercado tiene internet?") from None
    if not cuerpo.get("ok"):
        raise ErrorDeEnvio(f"Telegram rechazó el pedido: {cuerpo.get('description', '')}"[:300])
    return cuerpo["result"]


def enviar_telegram(config, chat_id, texto):
    if len(texto) > MAX_TELEGRAM:
        texto = texto[:MAX_TELEGRAM] + "\n… (sigue en el sistema)"
    _telegram(config.telegram_token, "sendMessage", {"chat_id": chat_id, "text": texto})


def enviar_email(config, para, asunto, texto):
    conexion = get_connection(
        host=config.email_host, port=config.email_puerto, username=config.email_usuario,
        password=config.email_password, use_tls=config.email_puerto != 465, use_ssl=config.email_puerto == 465,
        timeout=SEGUNDOS_DE_ESPERA,
    )
    mensaje = EmailMessage(asunto, texto, f"Sistema de Mercado <{config.email_usuario}>", [para], connection=conexion)
    try:
        mensaje.send()
    except smtplib.SMTPAuthenticationError:
        raise ErrorDeEnvio("El correo o la contraseña de aplicación no son correctos.") from None
    except (smtplib.SMTPException, OSError) as e:
        raise ErrorDeEnvio(f"No se pudo enviar el correo ({type(e).__name__}). ¿Hay internet?") from None


def enviar(envio, config=None, ahora=None):
    """Intenta un envío y deja anotado cómo salió. Devuelve True si se mandó."""
    config = config or ConfiguracionNotificaciones.actual()
    ahora = ahora or timezone.now()
    aviso = envio.notificacion
    envio.intentos += 1
    try:
        if envio.canal == Envio.TELEGRAM:
            enviar_telegram(config, envio.destino, aviso.texto)
        else:
            enviar_email(config, envio.destino, f"{aviso.titulo} — Sistema de Mercado", aviso.texto)
    except ErrorDeEnvio as e:
        envio.error = str(e)[:300]
        if envio.intentos >= MAX_INTENTOS:
            envio.estado = Envio.FALLIDO
        else:
            envio.proximo_intento = ahora + timedelta(minutes=min(2 ** (envio.intentos - 1), 30))
        envio.save()
        return False
    envio.estado, envio.enviado_en, envio.error = Envio.ENVIADO, ahora, ""
    envio.save()
    return True


def enviar_pendientes(ahora=None):
    """Manda lo que está en cola. Lo llama el planificador cada pocos segundos. Devuelve cuántos salieron."""
    ahora = ahora or timezone.now()
    pendientes = list(Envio.objects.filter(estado=Envio.PENDIENTE, proximo_intento__lte=ahora)
                      .select_related("notificacion")[:MAX_POR_VUELTA])
    if not pendientes:
        return 0
    config = ConfiguracionNotificaciones.actual()
    return sum(enviar(envio, config, ahora) for envio in pendientes)


# ---------- Configurar ----------

def verificar_bot(token):
    """Comprueba el token con Telegram y devuelve el nombre de usuario del bot."""
    return _telegram(token, "getMe")["username"]


def vincular_telegram(usuario, config=None):
    """Busca el mensaje «/start <código>» que el dueño le mandó al bot y guarda su chat. True si lo encontró."""
    config = config or ConfiguracionNotificaciones.actual()
    if not config.telegram_listo:
        raise ErrorDeEnvio("Primero hay que cargar el bot de Telegram del mercado.")
    vinculo = vinculo_de(usuario)
    esperado = f"/start {vinculo.codigo}"
    for novedad in reversed(_telegram(config.telegram_token, "getUpdates", {"allowed_updates": ["message"]})):
        mensaje = novedad.get("message") or {}
        if (mensaje.get("text") or "").strip() != esperado:
            continue
        chat = mensaje.get("chat") or {}
        vinculo.chat_id = str(chat.get("id", ""))
        vinculo.nombre = (chat.get("first_name") or chat.get("username") or "")[:100]
        vinculo.vinculado_en = timezone.now()
        vinculo.save()
        try:
            enviar_telegram(config, vinculo.chat_id,
                            f"Listo, {usuario.nombre}. Acá te va a llegar la caja del día del mercado, "
                            f"todas las noches a las {TEXTO_HORA_DE_CIERRE}.")
        except ErrorDeEnvio:
            pass  # el vínculo ya quedó guardado
        return True
    return False


def desvincular_telegram(usuario):
    """Olvida el Telegram del dueño y le da un código nuevo (el enlace viejo deja de servir)."""
    VinculoTelegram.objects.filter(usuario=usuario).update(
        chat_id="", nombre="", vinculado_en=None, codigo=secrets.token_hex(5)
    )


def probar(usuario):
    """Manda ahora mismo un aviso de prueba a este dueño por los tres canales y dice cómo salió cada uno."""
    config = ConfiguracionNotificaciones.actual()
    titulo = "Aviso de prueba"
    texto = (f"AVISO DE PRUEBA\nHola {usuario.nombre}: si estás leyendo esto, los avisos del Sistema de Mercado "
             f"te llegan bien por acá.\nTodas las noches a las {TEXTO_HORA_DE_CIERRE} vas a recibir la caja del día.")
    aviso = crear_aviso(usuario, titulo, texto, config=config)
    resultados = [{"canal": "SISTEMA", "nombre": "Dentro del sistema", "ok": True,
                   "detalle": "Quedó en la pantalla «Avisos»."}]
    envios = {e.canal: e for e in aviso.envios.all()}
    faltantes = {
        Envio.TELEGRAM: ("Falta cargar el bot de Telegram del mercado." if not config.telegram_listo
                         else "Falta vincular tu Telegram."),
        Envio.EMAIL: ("Falta cargar la cuenta de correo desde la que manda el sistema." if not config.email_listo
                      else "Falta anotar tu correo."),
    }
    for canal, nombre in Envio.CANALES:
        envio = envios.get(canal)
        if envio is None:
            resultados.append({"canal": canal, "nombre": nombre, "ok": False, "detalle": faltantes[canal]})
            continue
        ok = enviar(envio, config)
        if not ok:  # es una prueba: no se reintenta sola
            Envio.objects.filter(pk=envio.pk).update(estado=Envio.FALLIDO)
        resultados.append({"canal": canal, "nombre": nombre, "ok": ok,
                           "detalle": "Enviado: fijate si te llegó." if ok else envio.error})
    return resultados
