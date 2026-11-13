from django.urls import path

from . import api

urlpatterns = [
    path("turnos/", api.TurnosView.as_view(), name="turnos"),
    path("turnos/<int:pk>/corregir/", api.CorregirTurnoView.as_view(), name="turno_corregir"),
    path("actividad/", api.ActividadView.as_view(), name="actividad"),
    path("resumen/", api.ResumenView.as_view(), name="resumen"),
    path("cierres/", api.CierresView.as_view(), name="cierres"),
    path("resultados/", api.ResultadosView.as_view(), name="resultados"),
]
