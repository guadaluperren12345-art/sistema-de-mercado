from django.urls import path

from . import api

urlpatterns = [
    path("notificaciones/", api.NotificacionesView.as_view(), name="notificaciones"),
    path("notificaciones/leer/", api.LeerView.as_view(), name="notificaciones_leer"),
    path("notificaciones/configuracion/", api.ConfiguracionView.as_view(), name="notificaciones_configuracion"),
    path("notificaciones/telegram/vincular/", api.VincularTelegramView.as_view(), name="telegram_vincular"),
    path("notificaciones/telegram/desvincular/", api.DesvincularTelegramView.as_view(), name="telegram_desvincular"),
    path("notificaciones/probar/", api.ProbarView.as_view(), name="notificaciones_probar"),
]
