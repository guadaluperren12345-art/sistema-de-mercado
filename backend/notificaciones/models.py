"""Avisos a los dueños (RF-123 a RF-131).

Cada noche a las 00:45 el sistema hace la caja del día y se la manda a cada dueño por tres
caminos, por si alguno falla: un aviso dentro del sistema, un mensaje de Telegram y un correo.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class ConfiguracionNotificaciones(models.Model):
    """Datos para poder mandar los avisos. Hay una sola fila; la cargan los dueños desde la pantalla.

    El token del bot y la contraseña del correo nunca se devuelven por la API.
    """

    # Telegram: el bot del mercado (se crea una vez con @BotFather)
    telegram_token = models.CharField(max_length=100, blank=True, default="")
    telegram_bot = models.CharField(max_length=100, blank=True, default="")  # nombre de usuario del bot

    # Correo: la cuenta desde la que el sistema manda los mails (por ejemplo un Gmail del mercado)
    email_host = models.CharField(max_length=100, default="smtp.gmail.com")
    email_puerto = models.IntegerField(default=587)
    email_usuario = models.CharField(max_length=100, blank=True, default="")
    email_password = models.CharField(max_length=100, blank=True, default="")

    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name="+"
    )
    actualizado_en = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "configuracion_notificaciones"
        verbose_name = "configuración de notificaciones"
        verbose_name_plural = "configuración de notificaciones"

    @classmethod
    def actual(cls):
        return cls.objects.get_or_create(pk=1)[0]

    @property
    def telegram_listo(self):
        return bool(self.telegram_token)

    @property
    def email_listo(self):
        return bool(self.email_usuario and self.email_password)


class VinculoTelegram(models.Model):
    """El Telegram de un dueño. Se vincula abriendo el bot con un código propio de esa persona."""

    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="telegram")
    codigo = models.CharField(max_length=20)  # viaja en el enlace t.me/<bot>?start=<codigo>
    chat_id = models.CharField(max_length=30, blank=True, default="")  # vacío = todavía no vinculó
    nombre = models.CharField(max_length=100, blank=True, default="")  # cómo se llama en Telegram
    vinculado_en = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "vinculo_telegram"
        verbose_name = "Telegram de un dueño"
        verbose_name_plural = "Telegram de los dueños"

    @property
    def vinculado(self):
        return bool(self.chat_id)


class Notificacion(models.Model):
    """Un aviso para un dueño. Es lo que se ve dentro del sistema; no se borra ni se modifica."""

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notificaciones")
    # El cierre del día que se avisa (vacío en los avisos de prueba)
    cierre = models.ForeignKey("turnos.CierreDiario", on_delete=models.CASCADE, blank=True, null=True,
                               related_name="notificaciones")
    titulo = models.CharField(max_length=150)
    texto = models.TextField()
    creada_en = models.DateTimeField(default=timezone.now)
    leida_en = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "notificacion"
        verbose_name = "notificación"
        verbose_name_plural = "notificaciones"
        ordering = ["-creada_en", "-id"]

    def __str__(self):
        return f"{self.titulo} → {self.usuario_id}"


class Envio(models.Model):
    """El envío de un aviso por un canal de afuera (Telegram o correo), con sus reintentos.

    Si a las 00:45 no hay internet, queda pendiente y el planificador lo vuelve a intentar.
    """

    TELEGRAM = "TELEGRAM"
    EMAIL = "EMAIL"
    CANALES = [(TELEGRAM, "Telegram"), (EMAIL, "Correo")]

    PENDIENTE = "PENDIENTE"
    ENVIADO = "ENVIADO"
    FALLIDO = "FALLIDO"
    ESTADOS = [(PENDIENTE, "Pendiente"), (ENVIADO, "Enviado"), (FALLIDO, "No se pudo enviar")]

    notificacion = models.ForeignKey(Notificacion, on_delete=models.CASCADE, related_name="envios")
    canal = models.CharField(max_length=10, choices=CANALES)
    destino = models.CharField(max_length=100)  # el chat de Telegram o la dirección de correo
    estado = models.CharField(max_length=10, choices=ESTADOS, default=PENDIENTE)
    intentos = models.IntegerField(default=0)
    proximo_intento = models.DateTimeField(default=timezone.now)
    enviado_en = models.DateTimeField(blank=True, null=True)
    error = models.CharField(max_length=300, blank=True, default="")

    class Meta:
        db_table = "envio_notificacion"
        verbose_name = "envío de notificación"
        verbose_name_plural = "envíos de notificaciones"
        ordering = ["id"]
