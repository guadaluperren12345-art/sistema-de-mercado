"""Pruebas de turnos, horas trabajadas, cierre de las 00:00, actividad y resumen.

Ejecutar con:  docker compose exec backend python manage.py test turnos
"""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APITestCase

from productos.models import Categoria, MovimientoStock, Producto
from usuarios.models import RegistroAcceso, Rol, Usuario

from . import servicios
from .models import CierreDiario, Turno

PASSWORD = "Mercado2026"


class Base(APITestCase):
    def setUp(self):
        self.usuarios = {}
        for i, rol in enumerate((Rol.ADMINISTRADOR, Rol.ENCARGADO, Rol.EMPLEADO), start=1):
            self.usuarios[rol] = Usuario.objects.create_user(
                rol.lower(), PASSWORD, nombre=rol, apellido="Test", dni=f"2000000{i}",
                rol=Rol.objects.get(nombre=rol), debe_cambiar_password=False,
            )
        self.dueño = self.usuarios[Rol.ADMINISTRADOR]
        self.empleado = self.usuarios[Rol.EMPLEADO]

    def login(self, rol):
        datos = {"nombre_usuario": self.usuarios[rol].nombre_usuario, "password": PASSWORD}
        return self.client.post("/api/auth/login/", datos).data

    def entrar_como(self, rol):
        datos = self.login(rol)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {datos['access']}")
        return datos

    def mover_al_pasado(self, turno, dias=1, hora=14):
        """Deja un turno como si hubiera empezado hace `dias` días a esa hora."""
        ayer = timezone.localdate() - timedelta(days=dias)
        inicio = servicios.inicio_del_dia(ayer) + timedelta(hours=hora)
        Turno.objects.filter(pk=turno.pk).update(inicio=inicio, ultima_actividad=inicio + timedelta(hours=3))
        turno.refresh_from_db()
        return turno


class TurnoAlEntrarYSalirTests(Base):
    def test_login_abre_turno_y_logout_lo_cierra(self):  # RF-21, RF-23, RF-25
        datos = self.login(Rol.EMPLEADO)
        turno = Turno.objects.get(usuario=self.empleado)
        self.assertTrue(turno.abierto)

        r = self.client.post("/api/auth/logout/", {"refresh": datos["refresh"]})
        self.assertEqual(r.status_code, 204)
        turno.refresh_from_db()
        self.assertFalse(turno.abierto)
        self.assertEqual(turno.tipo_cierre, Turno.USUARIO)
        self.assertFalse(turno.para_revisar)

    def test_los_dueños_no_llevan_turno(self):
        self.login(Rol.ADMINISTRADOR)
        self.assertEqual(Turno.objects.count(), 0)

    def test_segundo_login_sigue_con_el_mismo_turno(self):  # RN-07
        self.login(Rol.EMPLEADO)
        self.login(Rol.EMPLEADO)
        self.assertEqual(Turno.objects.filter(usuario=self.empleado).count(), 1)

    def test_cada_ingreso_del_dia_es_un_turno_distinto(self):
        datos = self.login(Rol.EMPLEADO)
        self.client.post("/api/auth/logout/", {"refresh": datos["refresh"]})
        self.login(Rol.EMPLEADO)
        self.assertEqual(Turno.objects.filter(usuario=self.empleado).count(), 2)
        self.assertEqual(Turno.objects.filter(usuario=self.empleado, fin__isnull=True).count(), 1)

    def test_logout_por_inactividad_queda_marcado(self):  # RF-06
        datos = self.login(Rol.EMPLEADO)
        self.client.post("/api/auth/logout/", {"refresh": datos["refresh"], "motivo": "inactividad"})
        self.assertEqual(Turno.objects.get(usuario=self.empleado).tipo_cierre, Turno.INACTIVIDAD)
        self.assertTrue(RegistroAcceso.objects.filter(usuario=self.empleado, tipo="LOGOUT").exists())

    def test_logout_con_token_inventado_no_cierra_nada(self):
        self.login(Rol.EMPLEADO)
        r = self.client.post("/api/auth/logout/", {"refresh": "esto.no.esuntoken"})
        self.assertEqual(r.status_code, 401)
        self.assertTrue(Turno.objects.get(usuario=self.empleado).abierto)

    def test_al_cerrar_el_turno_se_corta_la_sesion(self):
        datos = self.entrar_como(Rol.EMPLEADO)
        self.assertEqual(self.client.get("/api/auth/yo/").status_code, 200)
        servicios.cerrar_turno(self.empleado, Turno.ADMINISTRADOR)
        self.assertEqual(self.client.get("/api/auth/yo/").status_code, 401)
        self.client.credentials()
        self.assertEqual(self.client.post("/api/auth/refresh/", {"refresh": datos["refresh"]}).status_code, 401)

    def test_dar_de_baja_a_alguien_termina_su_turno(self):
        self.login(Rol.EMPLEADO)
        self.entrar_como(Rol.ADMINISTRADOR)
        self.client.post(f"/api/usuarios/{self.empleado.pk}/desactivar/")
        turno = Turno.objects.get(usuario=self.empleado)
        self.assertEqual(turno.tipo_cierre, Turno.ADMINISTRADOR)


class CierreDeLas00Tests(Base):
    def test_turno_olvidado_se_cierra_a_las_00_y_queda_para_revisar(self):  # RF-27
        self.login(Rol.EMPLEADO)
        turno = self.mover_al_pasado(Turno.objects.get(usuario=self.empleado), dias=1, hora=14)

        servicios.cerrar_dias_pendientes()

        turno.refresh_from_db()
        self.assertEqual(turno.fin, servicios.inicio_del_dia(timezone.localdate()))  # 00:00 en punto
        self.assertEqual(turno.tipo_cierre, Turno.SISTEMA)
        self.assertTrue(turno.para_revisar)
        self.assertEqual(turno.minutos, 10 * 60)  # de 14:00 a 00:00

    def test_genera_el_cierre_de_cada_dia_terminado_una_sola_vez(self):
        self.login(Rol.EMPLEADO)
        self.mover_al_pasado(Turno.objects.get(usuario=self.empleado), dias=3, hora=8)

        servicios.cerrar_dias_pendientes()
        servicios.cerrar_dias_pendientes()  # repetirlo no duplica nada

        hoy = timezone.localdate()
        fechas = list(CierreDiario.objects.order_by("fecha").values_list("fecha", flat=True))
        self.assertEqual(fechas, [hoy - timedelta(days=d) for d in (3, 2, 1)])
        primero = CierreDiario.objects.get(fecha=hoy - timedelta(days=3))
        self.assertEqual(primero.turnos, 1)
        self.assertEqual(primero.minutos_trabajados, 16 * 60)
        self.assertEqual(primero.turnos_cerrados_por_sistema, 1)

    def test_el_dia_de_hoy_no_se_cierra_antes_de_tiempo(self):
        self.login(Rol.EMPLEADO)
        servicios.cerrar_dias_pendientes()
        self.assertTrue(Turno.objects.get(usuario=self.empleado).abierto)
        self.assertEqual(CierreDiario.objects.count(), 0)

    def test_sesion_de_ayer_no_sirve_despues_de_las_00(self):
        self.entrar_como(Rol.EMPLEADO)
        self.mover_al_pasado(Turno.objects.get(usuario=self.empleado))
        # Aunque el planificador no haya pasado, el primer pedido cierra el turno y corta la sesión
        self.assertEqual(self.client.get("/api/auth/yo/").status_code, 401)
        self.assertFalse(Turno.objects.get(usuario=self.empleado).abierto)

    def test_al_volver_a_entrar_empieza_un_turno_nuevo(self):
        self.login(Rol.EMPLEADO)
        self.mover_al_pasado(Turno.objects.get(usuario=self.empleado))
        self.login(Rol.EMPLEADO)  # el login pone al día los cierres
        self.assertEqual(Turno.objects.filter(usuario=self.empleado).count(), 2)
        self.assertEqual(CierreDiario.objects.count(), 1)


class HorariosSoloParaDueñosTests(Base):
    def test_encargado_y_empleado_no_ven_horarios_ni_actividad(self):
        for rol in (Rol.ENCARGADO, Rol.EMPLEADO):
            self.entrar_como(rol)
            for ruta in ("/api/turnos/", "/api/actividad/", "/api/resumen/", "/api/cierres/"):
                self.assertEqual(self.client.get(ruta).status_code, 403, f"{rol} {ruta}")
            self.assertEqual(self.client.post("/api/turnos/1/corregir/", {}).status_code, 403)

    def test_dueño_ve_quien_esta_trabajando_ahora(self):  # RF-28
        self.login(Rol.EMPLEADO)
        self.entrar_como(Rol.ADMINISTRADOR)
        r = self.client.get("/api/turnos/?estado=abiertos")
        self.assertEqual(r.status_code, 200)
        self.assertEqual([t["usuario"]["nombre"] for t in r.data], ["Empleado Test"])
        self.assertTrue(r.data[0]["abierto"])

    def test_turnos_del_dia_con_minutos(self):  # RF-26
        datos = self.login(Rol.EMPLEADO)
        turno = Turno.objects.get(usuario=self.empleado)
        Turno.objects.filter(pk=turno.pk).update(inicio=turno.inicio - timedelta(minutes=90))
        self.client.post("/api/auth/logout/", {"refresh": datos["refresh"]})
        self.entrar_como(Rol.ADMINISTRADOR)
        r = self.client.get("/api/turnos/")
        # Si la prueba corre justo antes de las 00:00 el turno pudo empezar "ayer": se aceptan ambos días
        ayer = (timezone.localdate() - timedelta(days=1)).isoformat()
        r = r if r.data else self.client.get(f"/api/turnos/?desde={ayer}&hasta={ayer}")
        self.assertEqual(len(r.data), 1)
        self.assertIn(r.data[0]["minutos"], (90, 91))

    def test_fechas_mal_escritas(self):
        self.entrar_como(Rol.ADMINISTRADOR)
        self.assertEqual(self.client.get("/api/turnos/?desde=ayer").status_code, 400)
        self.assertEqual(self.client.get("/api/resumen/?desde=2026-02-10&hasta=2026-02-01").status_code, 400)
        self.assertEqual(self.client.get("/api/actividad/?desde=x&hasta=y").status_code, 400)


class CorregirTurnoTests(Base):
    def setUp(self):
        super().setUp()
        self.login(Rol.EMPLEADO)
        self.turno = self.mover_al_pasado(Turno.objects.get(usuario=self.empleado), dias=1, hora=14)
        servicios.cerrar_dias_pendientes()
        self.turno.refresh_from_db()
        self.entrar_como(Rol.ADMINISTRADOR)

    def corregir(self, **datos):
        return self.client.post(f"/api/turnos/{self.turno.pk}/corregir/", datos)

    def test_aparece_en_la_lista_para_revisar(self):
        r = self.client.get("/api/turnos/?estado=revisar")
        self.assertEqual([t["id"] for t in r.data], [self.turno.pk])
        self.assertEqual(r.data[0]["tipo_cierre"], "SISTEMA")

    def test_corregir_la_hora_de_salida(self):
        salida = self.turno.inicio + timedelta(hours=6)  # se fue a las 20:00
        r = self.corregir(fin=salida.isoformat(), nota="Se fue a las 20")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["minutos"], 360)
        self.assertFalse(r.data["para_revisar"])
        self.assertEqual(r.data["corregido_por"], "Administrador Test")
        self.turno.refresh_from_db()
        # Queda guardada la hora que había puesto el sistema
        self.assertEqual(self.turno.fin_original, servicios.inicio_del_dia(timezone.localdate()))
        self.assertEqual(self.turno.nota, "Se fue a las 20")

    def test_confirmar_sin_cambiar_la_hora(self):
        r = self.corregir()
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["para_revisar"])
        self.assertEqual(r.data["minutos"], 600)

    def test_horas_imposibles(self):
        self.assertEqual(self.corregir(fin=(self.turno.inicio - timedelta(hours=1)).isoformat()).status_code, 400)
        self.assertEqual(self.corregir(fin=(self.turno.fin + timedelta(hours=1)).isoformat()).status_code, 400)
        self.assertEqual(self.corregir(fin="no es una hora").status_code, 400)
        self.turno.refresh_from_db()
        self.assertTrue(self.turno.para_revisar)

    def test_cerrar_un_turno_abierto_corta_la_sesion(self):
        datos = self.login(Rol.ENCARGADO)
        abierto = Turno.objects.get(usuario=self.usuarios[Rol.ENCARGADO])
        Turno.objects.filter(pk=abierto.pk).update(inicio=abierto.inicio - timedelta(minutes=30))
        self.assertEqual(self.client.post(f"/api/turnos/{abierto.pk}/corregir/", {}).status_code, 400)
        r = self.client.post(f"/api/turnos/{abierto.pk}/corregir/", {"fin": timezone.now().isoformat()})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["tipo_cierre"], "ADMINISTRADOR")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {datos['access']}")
        self.assertEqual(self.client.get("/api/auth/yo/").status_code, 401)


class ActividadYResumenTests(Base):
    def setUp(self):
        super().setUp()
        self.entrar_como(Rol.ENCARGADO)
        pollo = Categoria.objects.get(seccion__nombre="Carnicería", nombre="Pollo")
        r = self.client.post("/api/productos/", {
            "nombre": "Pechuga", "categoria": pollo.id, "unidad": "KG",
            "precio_venta": "6500.00", "precio_costo": "4000.00",
        })
        self.producto = Producto.objects.get(pk=r.data["id"])
        self.client.post(f"/api/productos/{self.producto.pk}/ingreso/", {"cantidad": "10"})
        self.client.post(f"/api/productos/{self.producto.pk}/perdida/", {"cantidad": "1.5", "motivo": "Vencido"})
        self.entrar_como(Rol.ADMINISTRADOR)
        ahora = timezone.now()
        self.desde = (ahora - timedelta(hours=1)).isoformat()
        self.hasta = (ahora + timedelta(hours=1)).isoformat()

    def test_actividad_muestra_todo_y_quien_estaba_de_turno(self):
        r = self.client.get("/api/actividad/", {"desde": self.desde, "hasta": self.hasta})
        self.assertEqual(r.status_code, 200, r.data)
        titulos = [e["titulo"] for e in r.data["eventos"]]
        for esperado in ("Inicio de sesión", "Alta de producto", "Ingreso de mercadería", "Pérdida"):
            self.assertIn(esperado, titulos)
        self.assertEqual([t["usuario"]["nombre"] for t in r.data["de_turno"]], ["Encargado Test"])
        perdida = next(e for e in r.data["eventos"] if e["titulo"] == "Pérdida")
        self.assertEqual(perdida["quien"]["nombre"], "Encargado Test")
        self.assertIn("Vencido", perdida["detalle"])
        self.assertIn("1,5 kg", perdida["detalle"])

    def test_actividad_filtrada_por_persona_y_por_tipo(self):
        encargado = self.usuarios[Rol.ENCARGADO]
        r = self.client.get("/api/actividad/", {"desde": self.desde, "hasta": self.hasta,
                                                "usuario": encargado.pk, "grupo": "STOCK"})
        self.assertEqual({e["grupo"] for e in r.data["eventos"]}, {"STOCK"})
        self.assertEqual(len(r.data["eventos"]), 2)
        r = self.client.get("/api/actividad/", {"desde": self.desde, "hasta": self.hasta,
                                                "usuario": self.dueño.pk, "grupo": "STOCK"})
        self.assertEqual(r.data["eventos"], [])

    def test_actividad_fuera_de_horario_no_aparece(self):
        antes = timezone.now() - timedelta(days=2)
        r = self.client.get("/api/actividad/", {"desde": (antes - timedelta(hours=1)).isoformat(),
                                                "hasta": antes.isoformat()})
        self.assertEqual(r.data["eventos"], [])
        self.assertEqual(r.data["de_turno"], [])

    def test_resumen_del_dia(self):
        hoy = servicios.fecha_local(MovimientoStock.objects.first().fecha_hora).isoformat()
        r = self.client.get(f"/api/resumen/?desde={hoy}&hasta={hoy}")
        self.assertEqual(r.status_code, 200, r.data)
        m = r.data["mercaderia"]
        self.assertEqual(m["movimientos"], 2)
        self.assertEqual(Decimal(m["ingresos"]["valor"]), Decimal("40000.00"))  # 10 kg × $4000
        self.assertEqual(Decimal(m["perdidas"]["valor"]), Decimal("6000.00"))  # 1,5 kg × $4000
        self.assertEqual(m["por_seccion"][0]["seccion"], "Carnicería")
        fila = m["por_producto"][0]
        self.assertEqual((fila["nombre"], Decimal(fila["ingresado"]), Decimal(fila["perdido"])),
                         ("Pechuga", Decimal("10"), Decimal("1.5")))
        self.assertEqual(r.data["personal"]["turnos"], 1)
        self.assertEqual(r.data["personal"]["por_persona"][0]["nombre"], "Encargado Test")
        self.assertEqual(r.data["cambios"], 3)  # alta del producto + 2 movimientos
        self.assertEqual(len(r.data["por_dia"]), 1)

    def test_resumen_de_la_semana_trae_un_renglon_por_dia(self):
        hoy = timezone.localdate()
        r = self.client.get(f"/api/resumen/?desde={hoy - timedelta(days=6)}&hasta={hoy}")
        self.assertEqual(len(r.data["por_dia"]), 7)
