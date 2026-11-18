"""Pruebas de los avisos a los dueños: la caja del día por el sistema, Telegram y correo (RF-123 a RF-131).

Ejecutar con:  docker compose exec backend python manage.py test notificaciones
Nunca salen a internet: Telegram se simula y el correo queda en la bandeja de prueba de Django.
"""

from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.utils import timezone
from rest_framework.test import APITestCase

from core import dia
from turnos import servicios as turnos
from turnos.models import CierreDiario
from usuarios.models import Rol, Usuario

from . import servicios
from .models import ConfiguracionNotificaciones, Envio, Notificacion, VinculoTelegram

PASSWORD = "Mercado2026"
TOKEN = "123456:token-de-prueba"


class Base(APITestCase):
    def setUp(self):
        self.usuarios = {}
        for i, rol in enumerate((Rol.ADMINISTRADOR, Rol.ENCARGADO, Rol.EMPLEADO), start=1):
            self.usuarios[rol] = Usuario.objects.create_user(
                rol.lower(), PASSWORD, nombre=rol, apellido="Test", dni=f"2000000{i}",
                rol=Rol.objects.get(nombre=rol), debe_cambiar_password=False,
            )
        self.dueño = self.usuarios[Rol.ADMINISTRADOR]

    def entrar_como(self, rol):
        datos = {"nombre_usuario": self.usuarios[rol].nombre_usuario, "password": PASSWORD}
        r = self.client.post("/api/auth/login/", datos)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")

    def configurar_todo(self):
        """Bot y correo cargados, y el dueño con su Telegram vinculado y su correo anotado."""
        config = ConfiguracionNotificaciones.actual()
        config.telegram_token, config.telegram_bot = TOKEN, "mercado_bot"
        config.email_usuario, config.email_password = "mercado@example.com", "clave-de-aplicacion"
        config.save()
        VinculoTelegram.objects.update_or_create(usuario=self.dueño, defaults={"codigo": "abc123", "chat_id": "777"})
        self.dueño.email = "duenio@example.com"
        self.dueño.save(update_fields=["email"])
        return config

    def cierre_de_ayer(self):
        ayer = dia.hoy() - timedelta(days=1)
        cierre, _, r = turnos.generar_cierre(ayer)
        return cierre, r


class TextoDeLaCajaTests(Base):
    def test_pesos_en_formato_argentino(self):
        self.assertEqual(servicios.pesos("1234567.5"), "$1.234.567,50")
        self.assertEqual(servicios.pesos("-80"), "−$80,00")

    def test_el_texto_trae_toda_la_caja(self):
        cierre, r = self.cierre_de_ayer()
        titulo, texto = servicios.texto_de_caja(cierre, r)
        self.assertIn(f"{cierre.fecha:%d/%m/%Y}", titulo)
        for parte in ("RESULTADO DEL DÍA", "PLATA QUE ENTRÓ", "PLATA QUE SALIÓ", "Gastos",
                      "Pagos a comerciantes", "EFECTIVO QUE DEBERÍA HABER EN LA CAJA", "00:45"):
            self.assertIn(parte, texto)


class AvisarCierreTests(Base):
    def test_sin_configurar_nada_igual_queda_el_aviso_en_el_sistema(self):
        cierre, r = self.cierre_de_ayer()
        servicios.avisar_cierre(cierre, r)
        aviso = Notificacion.objects.get()
        self.assertEqual((aviso.usuario, aviso.cierre), (self.dueño, cierre))
        self.assertEqual(Envio.objects.count(), 0)

    def test_avisa_a_cada_dueño_activo_y_a_nadie_mas(self):
        otro = Usuario.objects.create_user("socio", PASSWORD, nombre="Socio", apellido="Test", dni="20000009",
                                           rol=Rol.objects.get(nombre=Rol.ADMINISTRADOR))
        Usuario.objects.create_user("exsocio", PASSWORD, nombre="Ex", apellido="Socio", dni="20000008",
                                    rol=Rol.objects.get(nombre=Rol.ADMINISTRADOR), activo=False)
        cierre, r = self.cierre_de_ayer()
        servicios.avisar_cierre(cierre, r)
        self.assertEqual(set(Notificacion.objects.values_list("usuario_id", flat=True)), {self.dueño.id, otro.id})

    def test_encola_telegram_y_correo_y_el_planificador_los_manda(self):
        self.configurar_todo()
        cierre, r = self.cierre_de_ayer()
        servicios.avisar_cierre(cierre, r)
        self.assertEqual(sorted(Envio.objects.values_list("canal", "destino", "estado")),
                         [("EMAIL", "duenio@example.com", "PENDIENTE"), ("TELEGRAM", "777", "PENDIENTE")])

        with patch.object(servicios, "_telegram") as telegram:
            self.assertEqual(servicios.enviar_pendientes(), 2)
        metodo, datos = telegram.call_args.args[1:]
        self.assertEqual((metodo, datos["chat_id"]), ("sendMessage", "777"))
        self.assertIn("RESULTADO DEL DÍA", datos["text"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["duenio@example.com"])
        self.assertIn("Caja del día", mail.outbox[0].subject)
        self.assertIn("RESULTADO DEL DÍA", mail.outbox[0].body)
        self.assertEqual(set(Envio.objects.values_list("estado", flat=True)), {"ENVIADO"})
        with patch.object(servicios, "_telegram") as telegram:
            self.assertEqual(servicios.enviar_pendientes(), 0)  # no se manda dos veces
        telegram.assert_not_called()

    def test_sin_internet_queda_pendiente_y_se_reintenta_mas_tarde(self):
        self.configurar_todo()
        self.dueño.email = None
        self.dueño.save(update_fields=["email"])
        cierre, r = self.cierre_de_ayer()
        servicios.avisar_cierre(cierre, r)
        ahora = timezone.now()
        with patch.object(servicios, "_telegram", side_effect=servicios.ErrorDeEnvio("No se pudo conectar")):
            self.assertEqual(servicios.enviar_pendientes(ahora), 0)
            envio = Envio.objects.get()
            self.assertEqual((envio.estado, envio.intentos, envio.error), ("PENDIENTE", 1, "No se pudo conectar"))
            self.assertGreater(envio.proximo_intento, ahora)
            self.assertEqual(servicios.enviar_pendientes(ahora), 0)  # todavía no le toca
            self.assertEqual(Envio.objects.get().intentos, 1)
        with patch.object(servicios, "_telegram"):
            self.assertEqual(servicios.enviar_pendientes(ahora + timedelta(minutes=5)), 1)
        self.assertEqual(Envio.objects.get().estado, "ENVIADO")

    def test_despues_de_muchos_intentos_se_da_por_fallido(self):
        self.configurar_todo()
        aviso = servicios.crear_aviso(self.dueño, "Prueba", "Texto")
        envio = aviso.envios.get(canal=Envio.TELEGRAM)
        envio.intentos = servicios.MAX_INTENTOS - 1
        with patch.object(servicios, "_telegram", side_effect=servicios.ErrorDeEnvio("x")):
            self.assertFalse(servicios.enviar(envio))
        self.assertEqual(Envio.objects.get(pk=envio.pk).estado, "FALLIDO")

    def test_un_error_al_avisar_no_frena_el_cierre(self):
        cierre, r = self.cierre_de_ayer()
        with patch.object(servicios, "texto_de_caja", side_effect=RuntimeError("boom")), self.assertLogs(level="ERROR"):
            self.assertEqual(servicios.avisar_cierre(cierre, r), [])
        self.assertTrue(CierreDiario.objects.filter(pk=cierre.pk).exists())


class ApiDeAvisosTests(Base):
    def test_solo_los_dueños(self):
        for rol in (Rol.ENCARGADO, Rol.EMPLEADO):
            self.entrar_como(rol)
            for ruta in ("/api/notificaciones/", "/api/notificaciones/configuracion/"):
                self.assertEqual(self.client.get(ruta).status_code, 403, f"{rol} {ruta}")
            self.assertEqual(self.client.post("/api/notificaciones/probar/").status_code, 403)

    def test_ver_y_marcar_como_leidos(self):
        for n in range(3):
            servicios.crear_aviso(self.dueño, f"Aviso {n}", "Texto")
        servicios.crear_aviso(self.usuarios[Rol.ENCARGADO], "Ajeno", "No lo ve el dueño")
        self.entrar_como(Rol.ADMINISTRADOR)

        r = self.client.get("/api/notificaciones/")
        self.assertEqual(r.data["sin_leer"], 3)
        self.assertEqual([a["titulo"] for a in r.data["notificaciones"]], ["Aviso 2", "Aviso 1", "Aviso 0"])
        self.assertEqual(self.client.get("/api/notificaciones/?solo=cuenta").data, {"sin_leer": 3})

        uno = r.data["notificaciones"][0]["id"]
        self.assertEqual(self.client.post("/api/notificaciones/leer/", {"id": uno}).data["sin_leer"], 2)
        self.assertEqual(self.client.post("/api/notificaciones/leer/").data["sin_leer"], 0)
        self.assertEqual(Notificacion.objects.filter(leida_en__isnull=True).count(), 1)  # el ajeno no se toca

    def test_cargar_el_bot_verifica_el_token_y_nunca_lo_devuelve(self):
        self.entrar_como(Rol.ADMINISTRADOR)
        with patch.object(servicios, "_telegram", return_value={"username": "mercado_bot"}) as telegram:
            r = self.client.put("/api/notificaciones/configuracion/", {"telegram_token": TOKEN})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(telegram.call_args.args[:2], (TOKEN, "getMe"))
        self.assertTrue(r.data["telegram"]["configurado"])
        self.assertTrue(r.data["telegram"]["enlace"].startswith("https://t.me/mercado_bot?start="))
        self.assertNotIn(TOKEN, str(r.data))
        self.assertEqual(ConfiguracionNotificaciones.actual().telegram_token, TOKEN)

    def test_token_invalido_no_se_guarda(self):
        self.entrar_como(Rol.ADMINISTRADOR)
        with patch.object(servicios, "_telegram", side_effect=servicios.ErrorDeEnvio("El token del bot de Telegram no es válido.")):
            r = self.client.put("/api/notificaciones/configuracion/", {"telegram_token": "cualquiera"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(ConfiguracionNotificaciones.actual().telegram_token, "")

    def test_cargar_el_correo(self):
        self.entrar_como(Rol.ADMINISTRADOR)
        r = self.client.put("/api/notificaciones/configuracion/", {
            "email_usuario": "mercado@example.com", "email_password": "abcd efgh ijkl mnop", "mi_email": "yo@example.com",
        })
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["email"], {"configurado": True, "host": "smtp.gmail.com", "puerto": 587,
                                           "usuario": "mercado@example.com", "mi_email": "yo@example.com"})
        self.assertNotIn("abcd", str(r.data))
        self.assertEqual(ConfiguracionNotificaciones.actual().email_password, "abcdefghijklmnop")
        self.assertEqual(r.data["dueños"], [{"id": self.dueño.id, "nombre": "Administrador Test",
                                             "telegram": False, "email": True}])
        r = self.client.put("/api/notificaciones/configuracion/", {"mi_email": "esto no es un correo"})
        self.assertEqual(r.status_code, 400)

    def test_vincular_mi_telegram_con_el_codigo(self):
        self.configurar_todo()
        VinculoTelegram.objects.filter(usuario=self.dueño).update(chat_id="")
        self.entrar_como(Rol.ADMINISTRADOR)
        codigo = self.client.get("/api/notificaciones/configuracion/").data["telegram"]["codigo"]

        novedades = [{"message": {"text": "/start otro-codigo", "chat": {"id": 1, "first_name": "Intruso"}}}]
        with patch.object(servicios, "_telegram", return_value=novedades):
            r = self.client.post("/api/notificaciones/telegram/vincular/")
        self.assertEqual(r.status_code, 400)  # todavía no escribió al bot con su código

        novedades.append({"message": {"text": f"/start {codigo}", "chat": {"id": 4242, "first_name": "Lupe"}}})
        with patch.object(servicios, "_telegram", return_value=novedades):
            r = self.client.post("/api/notificaciones/telegram/vincular/")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual((r.data["telegram"]["vinculado"], r.data["telegram"]["mi_nombre"]), (True, "Lupe"))
        self.assertEqual(VinculoTelegram.objects.get(usuario=self.dueño).chat_id, "4242")

        r = self.client.post("/api/notificaciones/telegram/desvincular/")
        self.assertFalse(r.data["telegram"]["vinculado"])
        self.assertNotEqual(r.data["telegram"]["codigo"], codigo)  # el enlace viejo ya no sirve

    def test_aviso_de_prueba_dice_como_salio_cada_canal(self):
        self.entrar_como(Rol.ADMINISTRADOR)
        r = self.client.post("/api/notificaciones/probar/")
        self.assertEqual([(x["canal"], x["ok"]) for x in r.data["resultados"]],
                         [("SISTEMA", True), ("TELEGRAM", False), ("EMAIL", False)])
        self.assertIn("Falta cargar el bot", r.data["resultados"][1]["detalle"])

        self.configurar_todo()
        with patch.object(servicios, "_telegram", side_effect=servicios.ErrorDeEnvio("Sin internet")):
            r = self.client.post("/api/notificaciones/probar/")
        self.assertEqual([(x["canal"], x["ok"]) for x in r.data["resultados"]],
                         [("SISTEMA", True), ("TELEGRAM", False), ("EMAIL", True)])
        self.assertEqual(r.data["resultados"][1]["detalle"], "Sin internet")
        self.assertEqual(Envio.objects.filter(estado="PENDIENTE").count(), 0)  # una prueba no se reintenta sola
        self.assertEqual(len(mail.outbox), 1)
