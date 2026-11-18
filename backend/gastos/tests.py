"""Pruebas de la lista de gastos y de cómo influye en el cierre del día (RF-106 a RF-111).

Ejecutar con:  docker compose exec backend python manage.py test gastos
"""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APITestCase

from core import dia

from productos.models import Categoria, Producto
from turnos import servicios as turnos
from usuarios.models import Rol, Usuario

from .models import Gasto

PASSWORD = "Mercado2026"


class Base(APITestCase):
    def setUp(self):
        self.usuarios = {}
        for i, rol in enumerate((Rol.ADMINISTRADOR, Rol.ENCARGADO, Rol.EMPLEADO), start=1):
            self.usuarios[rol] = Usuario.objects.create_user(
                rol.lower(), PASSWORD, nombre=rol, apellido="Test", dni=f"2000000{i}",
                rol=Rol.objects.get(nombre=rol), debe_cambiar_password=False,
            )
        self.entrar_como(Rol.EMPLEADO)

    def entrar_como(self, rol):
        datos = {"nombre_usuario": self.usuarios[rol].nombre_usuario, "password": PASSWORD}
        token = self.client.post("/api/auth/login/", datos).data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def anotar(self, monto="2500", proposito="bolsas de residuos"):
        return self.client.post("/api/gastos/", {"monto": monto, "proposito": proposito}, format="json")


class GastosTests(Base):
    def test_cualquiera_anota_un_gasto(self):  # RF-106
        for rol in (Rol.EMPLEADO, Rol.ENCARGADO, Rol.ADMINISTRADOR):
            self.entrar_como(rol)
            r = self.anotar()
            self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["monto"], "2500.00")
        self.assertEqual(r.data["proposito"], "Bolsas de residuos")
        self.assertEqual(r.data["usuario"], "Administrador Test")
        empleado = Gasto.objects.get(usuario=self.usuarios[Rol.EMPLEADO])
        self.assertIsNotNone(empleado.turno)  # queda a nombre de quien lo anotó y en su turno

    def test_validaciones(self):
        self.assertIn("monto", self.anotar(monto="0").data)
        self.assertIn("monto", self.anotar(monto="-500").data)
        self.assertIn("monto", self.anotar(monto="mucho").data)
        self.assertIn("proposito", self.anotar(proposito="").data)
        self.assertIn("proposito", self.anotar(proposito="  x ").data)
        self.assertIn("monto", self.client.post("/api/gastos/", {"proposito": "Hielo"}, format="json").data)
        self.assertFalse(Gasto.objects.exists())

    def test_lista_del_dia_con_total(self):  # RF-107
        self.anotar("2500", "bolsas")
        self.anotar("1200.50", "hielo")
        r = self.client.get("/api/gastos/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.data["cantidad"], r.data["total"]), (2, "3700.50"))
        self.assertEqual([g["proposito"] for g in r.data["gastos"]], ["Hielo", "Bolsas"])  # lo más nuevo primero

    def test_otros_dias_solo_duenos_y_encargados(self):
        ayer = (dia.hoy() - timedelta(days=1)).isoformat()
        self.assertEqual(self.client.get(f"/api/gastos/?fecha={ayer}").status_code, 403)
        self.assertEqual(self.client.get("/api/gastos/?fecha=ayer").status_code, 400)
        self.entrar_como(Rol.ENCARGADO)
        r = self.client.get(f"/api/gastos/?fecha={ayer}")
        self.assertEqual((r.status_code, r.data["cantidad"], r.data["total"]), (200, 0, "0.00"))

    def test_anular(self):  # RF-108
        propio = self.anotar().data["id"]
        r = self.client.post(f"/api/gastos/{propio}/anular/", {"motivo": "Lo anoté dos veces"})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data["anulado"])
        self.assertEqual(r.data["anulado_por"], "Empleado Test")
        self.assertEqual(self.client.post(f"/api/gastos/{propio}/anular/").status_code, 400)  # ya estaba anulado
        lista = self.client.get("/api/gastos/").data
        self.assertEqual((lista["cantidad"], lista["total"], len(lista["gastos"])), (0, "0.00", 1))  # sigue a la vista, no suma

    def test_empleado_no_anula_gastos_ajenos_ni_viejos(self):
        self.entrar_como(Rol.ENCARGADO)
        ajeno = self.anotar().data["id"]
        self.entrar_como(Rol.EMPLEADO)
        self.assertEqual(self.client.post(f"/api/gastos/{ajeno}/anular/").status_code, 403)
        viejo = self.anotar().data["id"]
        Gasto.objects.filter(pk=viejo).update(fecha_hora=timezone.now() - timedelta(days=1))
        self.assertEqual(self.client.post(f"/api/gastos/{viejo}/anular/").status_code, 403)
        self.assertEqual(self.client.post("/api/gastos/99999/anular/").status_code, 404)
        self.entrar_como(Rol.ENCARGADO)  # un encargado sí puede
        self.assertEqual(self.client.post(f"/api/gastos/{viejo}/anular/").status_code, 200)


class CierreTests(Base):
    """Los gastos se restan en la cuenta final del día (RF-109, RF-110)."""

    def setUp(self):
        super().setUp()
        self.entrar_como(Rol.ADMINISTRADOR)
        pollo = Categoria.objects.get(seccion__nombre="Carnicería", nombre="Pollo")
        r = self.client.post("/api/productos/", {"nombre": "Pechuga", "categoria": pollo.id, "unidad": "KG",
                                                 "precio_venta": "6500.00", "precio_costo": "4000.00"})
        self.pechuga = Producto.objects.get(pk=r.data["id"])
        self.client.post(f"/api/productos/{self.pechuga.id}/ingreso/", {"cantidad": "50"})
        cliente = self.client.post("/api/clientes/", {"nombre": "Rosa Díaz"}, format="json").data["id"]

        def vender(kilos, medio, **extra):
            cuerpo = {"items": [{"producto": self.pechuga.id, "cantidad": kilos}], "medio_pago": medio, **extra}
            self.assertEqual(self.client.post("/api/ventas/", cuerpo, format="json").status_code, 201)

        vender("2", "EFECTIVO")                    # 13.000 en efectivo
        vender("1", "DEBITO")                      #  6.500 con débito
        vender("2", "CUENTA", cliente=cliente)     # 13.000 fiado: no entra plata
        self.client.post(f"/api/clientes/{cliente}/pago/", {"importe": "3000", "medio_pago": "EFECTIVO"}, format="json")
        self.anotar("2500", "bolsas")
        self.anotar("1500", "flete")
        anulado = self.anotar("9999", "error").data["id"]
        self.client.post(f"/api/gastos/{anulado}/anular/")

    def test_resumen_resta_los_gastos(self):
        hoy = dia.hoy()
        r = turnos.resumen(hoy, hoy)
        self.assertEqual((r["gastos"]["cantidad"], r["gastos"]["anulados"], r["gastos"]["total"]), (2, 1, "4000.00"))
        self.assertEqual([g["proposito"] for g in r["gastos"]["lista"]], ["Flete", "Bolsas"])
        # Entró: 13.000 + 6.500 de ventas cobradas + 3.000 de un pago de cuenta corriente = 22.500
        self.assertEqual(r["caja"], {"entro": "22500.00", "gastos": "4000.00", "pagos_comerciantes": "0.00",
                                     "resultado": "18500.00", "efectivo": "12000.00"})  # efectivo: 13.000 + 3.000 − 4.000
        self.assertEqual(r["por_dia"][0]["gastos"], "4000.00")

    def test_cierre_de_las_00_45(self):
        hoy = dia.hoy()
        cierre = turnos.generar_cierre(hoy)[0]
        cierre.refresh_from_db()
        self.assertEqual((cierre.gastos_cantidad, cierre.gastos_total), (2, Decimal("4000.00")))
        self.assertEqual((cierre.entro, cierre.resultado_dia, cierre.efectivo_esperado),
                         (Decimal("22500.00"), Decimal("18500.00"), Decimal("12000.00")))
        fila = self.client.get("/api/cierres/").data
        self.assertEqual(self.client.get("/api/cierres/").status_code, 200)
        self.assertIsInstance(fila, list)

    def test_los_gastos_pueden_dejar_el_dia_en_negativo(self):
        self.anotar("30000", "arreglo de la heladera")
        hoy = dia.hoy()
        self.assertEqual(turnos.resumen(hoy, hoy)["caja"]["resultado"], "-11500.00")

    def test_actividad(self):  # RF-111
        ahora = timezone.now()
        eventos = turnos.actividad(ahora - timedelta(hours=1), ahora + timedelta(minutes=1), grupo="GASTOS")["eventos"]
        titulos = [e["titulo"] for e in eventos]
        self.assertEqual((titulos.count("Gasto"), titulos.count("Gasto anulado")), (3, 1))
