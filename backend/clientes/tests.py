"""Pruebas de clientes y cuenta corriente (RF-95 a RF-105).

Ejecutar con:  docker compose exec backend python manage.py test clientes
"""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APITestCase

from core import dia

from productos.models import Categoria, Producto
from turnos import servicios as turnos
from usuarios.models import CambioUsuario, Rol, Usuario
from ventas.models import Venta

from .models import CambioCliente, Cliente, ConfiguracionCuentas, MovimientoCuenta

PASSWORD = "Mercado2026"


class Base(APITestCase):
    def setUp(self):
        self.usuarios = {}
        for i, rol in enumerate((Rol.ADMINISTRADOR, Rol.ENCARGADO, Rol.EMPLEADO), start=1):
            self.usuarios[rol] = Usuario.objects.create_user(
                rol.lower(), PASSWORD, nombre=rol, apellido="Test", dni=f"2000000{i}",
                rol=Rol.objects.get(nombre=rol), debe_cambiar_password=False,
            )
        self.entrar_como(Rol.ADMINISTRADOR)
        pollo = Categoria.objects.get(seccion__nombre="Carnicería", nombre="Pollo")
        r = self.client.post("/api/productos/", {
            "nombre": "Pechuga", "categoria": pollo.id, "unidad": "KG", "precio_venta": "6500.00",
            "precio_costo": "4000.00",
        })
        self.pechuga = Producto.objects.get(pk=r.data["id"])
        self.client.post(f"/api/productos/{self.pechuga.id}/ingreso/", {"cantidad": "50"})
        self.rosa = self.alta("Rosa Díaz").data["id"]

    def entrar_como(self, rol):
        datos = {"nombre_usuario": self.usuarios[rol].nombre_usuario, "password": PASSWORD}
        token = self.client.post("/api/auth/login/", datos).data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def alta(self, nombre, **datos):
        return self.client.post("/api/clientes/", {"nombre": nombre, **datos}, format="json")

    def fiar(self, kilos="1", cliente="rosa", **datos):
        """Vende pechuga ($ 6.500 el kilo) en cuenta corriente."""
        cuerpo = {"items": [{"producto": self.pechuga.id, "cantidad": kilos}], "medio_pago": "CUENTA",
                  "cliente": self.rosa if cliente == "rosa" else cliente, **datos}
        return self.client.post("/api/ventas/", cuerpo, format="json")

    def pagar(self, importe, medio="EFECTIVO", cliente=None):
        return self.client.post(f"/api/clientes/{cliente or self.rosa}/pago/",
                                {"importe": importe, "medio_pago": medio}, format="json")

    def saldo(self, cliente=None):
        return Cliente.objects.get(pk=cliente or self.rosa).saldo

    def limite_general(self, valor):
        return self.client.post("/api/cuentas/configuracion/", {"limite_general": valor}, format="json")


class ClientesTests(Base):
    def test_alta_y_lista(self):
        r = self.alta("  juan   pérez ", dni="30.111.222", telefono="11 5555-1234")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["nombre"], "Juan pérez")
        self.assertEqual(r.data["dni"], "30111222")
        self.assertEqual(r.data["saldo"], "0.00")
        self.assertTrue(CambioCliente.objects.filter(cliente_id=r.data["id"], accion="ALTA").exists())
        self.entrar_como(Rol.EMPLEADO)  # el cajero ve a los clientes para poder fiarles y cobrarles
        nombres = [c["nombre"] for c in self.client.get("/api/clientes/?activo=1").data]
        self.assertEqual(nombres, ["Juan pérez", "Rosa Díaz"])
        self.assertEqual(len(self.client.get("/api/clientes/?q=rosa").data), 1)

    def test_nombre_y_dni_no_se_repiten(self):
        self.assertIn("nombre", self.alta("ROSA DIAZ").data)
        self.alta("Juan Pérez", dni="30111222")
        self.assertIn("dni", self.alta("Otro Juan", dni="30.111.222").data)
        self.assertIn("dni", self.alta("Pedro", dni="12").data)
        self.assertIn("nombre", self.alta("ab").data)

    def test_quien_puede_cargar_clientes(self):  # RF-96
        self.entrar_como(Rol.EMPLEADO)
        self.assertEqual(self.alta("Uno Nuevo").status_code, 403)
        self.entrar_como(Rol.ENCARGADO)
        self.assertEqual(self.alta("Uno Nuevo").status_code, 403)  # todavía no lo autorizaron

        self.entrar_como(Rol.ADMINISTRADOR)
        encargado = self.usuarios[Rol.ENCARGADO]
        r = self.client.post(f"/api/usuarios/{encargado.id}/permiso-clientes/", {"permitir": True}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data["puede_gestionar_clientes"])
        self.assertTrue(CambioUsuario.objects.filter(usuario=encargado, accion="PERMISO").exists())

        self.entrar_como(Rol.ENCARGADO)
        self.assertTrue(self.client.get("/api/auth/yo/").data["gestiona_clientes"])
        self.assertEqual(self.alta("Uno Nuevo").status_code, 201)
        self.assertEqual(self.client.patch(f"/api/clientes/{self.rosa}/", {"telefono": "123"}, format="json").status_code, 200)

        self.entrar_como(Rol.ADMINISTRADOR)
        self.client.post(f"/api/usuarios/{encargado.id}/permiso-clientes/", {"permitir": False}, format="json")
        self.entrar_como(Rol.ENCARGADO)
        self.assertEqual(self.alta("Otro Más").status_code, 403)

    def test_el_permiso_es_solo_para_encargados(self):
        for rol in (Rol.EMPLEADO, Rol.ADMINISTRADOR):
            r = self.client.post(f"/api/usuarios/{self.usuarios[rol].id}/permiso-clientes/", {"permitir": True}, format="json")
            self.assertEqual(r.status_code, 400)
        self.entrar_como(Rol.ENCARGADO)
        r = self.client.post(f"/api/usuarios/{self.usuarios[Rol.ENCARGADO].id}/permiso-clientes/", {"permitir": True}, format="json")
        self.assertEqual(r.status_code, 403)  # nadie se da el permiso a sí mismo

    def test_editar_y_baja_quedan_en_el_historial(self):
        r = self.client.patch(f"/api/clientes/{self.rosa}/", {"nombre": "Rosa Díaz de López", "nota": "paga los viernes"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        detalle = CambioCliente.objects.get(cliente_id=self.rosa, accion="EDICION").detalle
        self.assertIn("Nombre: Rosa Díaz → Rosa Díaz de López", detalle)
        r = self.client.post(f"/api/clientes/{self.rosa}/desactivar/", {"motivo": "Se mudó"})
        self.assertFalse(r.data["activo"])
        self.assertEqual(self.client.post(f"/api/clientes/{self.rosa}/desactivar/").status_code, 400)
        self.assertEqual(self.fiar().status_code, 400)  # a un cliente dado de baja no se le fía
        self.assertTrue(self.client.post(f"/api/clientes/{self.rosa}/reactivar/").data["activo"])
        self.assertEqual(self.fiar().status_code, 201)


class FiadoTests(Base):
    def test_venta_fiada_suma_a_la_deuda(self):  # RF-99
        self.entrar_como(Rol.EMPLEADO)  # cualquier cajero le fía a un cliente ya cargado
        r = self.fiar("2")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["medio_pago_texto"], "Cuenta corriente (fiado)")
        self.assertEqual(r.data["cliente"], {"id": self.rosa, "nombre": "Rosa Díaz"})
        self.assertEqual(self.saldo(), Decimal("13000.00"))
        m = MovimientoCuenta.objects.get(cliente_id=self.rosa)
        self.assertEqual((m.tipo, m.importe, m.saldo_resultante, m.venta_id), ("COMPRA", Decimal("13000.00"), Decimal("13000.00"), r.data["id"]))
        self.assertEqual(Producto.objects.get(pk=self.pechuga.id).stock_actual, Decimal("48.000"))

    def test_fiado_necesita_cliente(self):
        self.assertEqual(self.fiar(cliente=None).status_code, 400)
        self.assertEqual(self.fiar(cliente=99999).status_code, 400)
        self.assertFalse(Venta.objects.exists())

    def test_venta_comun_no_toca_cuentas(self):
        r = self.client.post("/api/ventas/", {"items": [{"producto": self.pechuga.id, "cantidad": "1"}],
                                              "medio_pago": "EFECTIVO", "cliente": self.rosa}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertIsNone(r.data["cliente"])
        self.assertEqual(self.saldo(), 0)

    def test_limite_general(self):  # RF-100
        self.assertEqual(self.limite_general("10000").data["limite_general"], "10000.00")
        self.assertTrue(CambioCliente.objects.filter(accion="LIMITE_GENERAL", cliente__isnull=True).exists())
        cliente = self.client.get(f"/api/clientes/{self.rosa}/").data
        self.assertEqual((cliente["limite"], cliente["limite_vigente"], cliente["disponible"]), (None, "10000.00", "10000.00"))
        self.assertEqual(self.fiar("1").status_code, 201)          # 6.500: entra
        r = self.fiar("1")                                         # 13.000: se pasa
        self.assertEqual(r.status_code, 400)
        self.assertIn("límite", r.data["detail"])
        self.assertEqual(self.saldo(), Decimal("6500.00"))
        self.assertEqual(Venta.objects.count(), 1)
        self.assertEqual(Producto.objects.get(pk=self.pechuga.id).stock_actual, Decimal("49.000"))  # no descontó
        self.assertIsNone(self.limite_general(None).data["limite_general"])  # sin límite general
        self.assertEqual(self.fiar("1").status_code, 201)

    def test_limite_propio_del_cliente_gana_al_general(self):
        self.limite_general("10000")
        r = self.client.patch(f"/api/clientes/{self.rosa}/", {"limite": "20000"}, format="json")
        self.assertEqual(r.data["limite_vigente"], "20000.00")
        self.assertTrue(CambioCliente.objects.filter(cliente_id=self.rosa, accion="LIMITE").exists())
        self.assertEqual(self.fiar("3").status_code, 201)   # 19.500
        self.assertEqual(self.fiar("1").status_code, 400)
        self.assertEqual(self.client.get(f"/api/clientes/{self.rosa}/").data["disponible"], "500.00")
        # Con límite 0 no se le fía nada, aunque el general lo permita
        self.pagar("19500")
        self.client.patch(f"/api/clientes/{self.rosa}/", {"limite": "0"}, format="json")
        self.assertEqual(self.fiar("1").status_code, 400)
        # Sin límite propio vuelve a usar el general
        r = self.client.patch(f"/api/clientes/{self.rosa}/", {"limite": None}, format="json")
        self.assertEqual(r.data["limite_vigente"], "10000.00")

    def test_los_limites_los_fijan_solo_los_duenos(self):
        encargado = self.usuarios[Rol.ENCARGADO]
        self.client.post(f"/api/usuarios/{encargado.id}/permiso-clientes/", {"permitir": True}, format="json")
        self.entrar_como(Rol.ENCARGADO)
        self.assertEqual(self.limite_general("5000").status_code, 403)
        self.assertIn("limite", self.client.patch(f"/api/clientes/{self.rosa}/", {"limite": "99999"}, format="json").data)
        self.assertIn("limite", self.alta("Con Límite", limite="5000").data)
        self.assertEqual(self.alta("Sin Límite").status_code, 201)
        self.assertEqual(self.client.get("/api/cuentas/configuracion/").status_code, 200)  # verlo, sí

    def test_anular_una_venta_fiada_baja_la_deuda(self):
        venta = self.fiar("2").data["id"]
        r = self.client.post(f"/api/ventas/{venta}/anular/", {"motivo": "Se arrepintió"})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self.saldo(), 0)
        tipos = list(MovimientoCuenta.objects.filter(cliente_id=self.rosa).order_by("id").values_list("tipo", flat=True))
        self.assertEqual(tipos, ["COMPRA", "ANULACION"])

    def test_modificar_una_venta_fiada(self):
        venta = self.fiar("2").data["id"]  # 13.000
        cuerpo = {"items": [{"producto": self.pechuga.id, "cantidad": "3"}], "medio_pago": "CUENTA"}
        r = self.client.post(f"/api/ventas/{venta}/corregir/", cuerpo, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["cliente"]["id"], self.rosa)  # sigue a nombre del mismo cliente
        self.assertEqual(self.saldo(), Decimal("19500.00"))
        # Si al final paga en efectivo, ya no debe nada
        cuerpo["medio_pago"] = "EFECTIVO"
        r = self.client.post(f"/api/ventas/{r.data['id']}/corregir/", cuerpo, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(self.saldo(), 0)

    def test_modificar_no_puede_pasar_el_limite(self):
        self.limite_general("15000")
        venta = self.fiar("2").data["id"]
        cuerpo = {"items": [{"producto": self.pechuga.id, "cantidad": "3"}], "medio_pago": "CUENTA"}
        self.assertEqual(self.client.post(f"/api/ventas/{venta}/corregir/", cuerpo, format="json").status_code, 400)
        self.assertEqual(self.saldo(), Decimal("13000.00"))  # todo quedó como estaba
        self.assertFalse(Venta.objects.get(pk=venta).anulada)


class PagosTests(Base):
    def setUp(self):
        super().setUp()
        self.fiar("2")  # debe 13.000

    def test_pago_parcial_y_total(self):  # RF-101
        self.entrar_como(Rol.EMPLEADO)  # cualquier cajero cobra
        r = self.pagar("5000", "TRANSFERENCIA")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["saldo"], "8000.00")
        comprobante = r.data["comprobante"]
        self.assertEqual((comprobante["tipo"], comprobante["importe"], comprobante["saldo_resultante"]), ("PAGO", "-5000.00", "8000.00"))
        self.assertEqual(comprobante["medio_pago_texto"], "Transferencia")
        self.assertEqual(comprobante["usuario"], "Empleado Test")
        self.assertEqual(self.pagar("8000").data["saldo"], "0.00")
        self.assertEqual(self.pagar("100").status_code, 400)  # ya no debe nada

    def test_validaciones_del_pago(self):
        self.assertEqual(self.pagar("13000.01").status_code, 400)  # más de lo que debe
        self.assertEqual(self.pagar("0").status_code, 400)
        self.assertEqual(self.pagar("-5").status_code, 400)
        self.assertEqual(self.pagar("100", "CUENTA").status_code, 400)  # la deuda no se paga con fiado
        self.assertEqual(self.pagar("100", cliente=99999).status_code, 404)
        self.assertEqual(self.saldo(), Decimal("13000.00"))

    def test_movimientos_de_la_cuenta(self):  # RF-102
        self.pagar("3000")
        r = self.client.get(f"/api/clientes/{self.rosa}/movimientos/")
        self.assertEqual([(m["tipo"], m["importe"], m["saldo_resultante"]) for m in r.data],
                         [("PAGO", "-3000.00", "10000.00"), ("COMPRA", "13000.00", "13000.00")])
        self.assertIsNotNone(r.data[1]["venta_numero"])

    def test_ajuste_solo_duenos(self):  # RF-103
        r = self.client.post(f"/api/clientes/{self.rosa}/ajuste/", {"importe": "2500", "motivo": "Deuda del cuaderno"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["saldo"], "15500.00")
        self.client.post(f"/api/clientes/{self.rosa}/ajuste/", {"importe": "-500", "motivo": "Se cargó de más"}, format="json")
        self.assertEqual(self.saldo(), Decimal("15000.00"))
        self.assertEqual(self.client.post(f"/api/clientes/{self.rosa}/ajuste/", {"importe": "100"}, format="json").status_code, 400)
        self.assertEqual(self.client.post(f"/api/clientes/{self.rosa}/ajuste/", {"importe": "0", "motivo": "x"}, format="json").status_code, 400)
        self.entrar_como(Rol.ENCARGADO)
        r = self.client.post(f"/api/clientes/{self.rosa}/ajuste/", {"importe": "-15000", "motivo": "Trampa"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_resumen_cierre_y_actividad(self):  # RF-104
        self.pagar("5000", "EFECTIVO")
        self.pagar("1000", "QR")
        hoy = dia.hoy()
        r = turnos.resumen(hoy, hoy)
        self.assertEqual(r["ventas"]["fiado"], "13000.00")
        self.assertEqual(r["ventas"]["efectivo"], "0.00")  # lo fiado no es plata en la caja
        cuenta = r["cuenta_corriente"]
        self.assertEqual((cuenta["cobros"], cuenta["total"], cuenta["efectivo"]), (2, "6000.00", "5000.00"))
        cierre = turnos.generar_cierre(hoy)[0]
        cierre.refresh_from_db()
        self.assertEqual((cierre.ventas_fiado, cierre.cobros_cuenta, cierre.cobros_cuenta_efectivo),
                         (Decimal("13000.00"), Decimal("6000.00"), Decimal("5000.00")))
        ahora = timezone.now()
        eventos = turnos.actividad(ahora - timedelta(hours=1), ahora + timedelta(minutes=1), grupo="CLIENTES")["eventos"]
        titulos = [e["titulo"] for e in eventos]
        self.assertEqual(titulos.count("Pago de cuenta corriente"), 2)
        self.assertIn("Alta de cliente", titulos)
        self.assertIn("CLIENTES", turnos.GRUPOS)
