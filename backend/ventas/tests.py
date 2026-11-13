"""Pruebas de ventas, recibos, buzón y código de barras.

Ejecutar con:  docker compose exec backend python manage.py test ventas
"""

from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APITestCase

from productos.models import Categoria, MovimientoStock, Producto
from turnos import servicios
from turnos.models import CierreDiario
from usuarios.models import Rol, Usuario

from .models import Venta

PASSWORD = "Mercado2026"


class Base(APITestCase):
    def setUp(self):
        self.usuarios = {}
        for i, rol in enumerate((Rol.ADMINISTRADOR, Rol.ENCARGADO, Rol.EMPLEADO), start=1):
            self.usuarios[rol] = Usuario.objects.create_user(
                rol.lower(), PASSWORD, nombre=rol, apellido="Test", dni=f"2000000{i}",
                rol=Rol.objects.get(nombre=rol), debe_cambiar_password=False,
            )
        self.entrar_como(Rol.ENCARGADO)
        pollo = Categoria.objects.get(seccion__nombre="Carnicería", nombre="Pollo")
        bebidas = Categoria.objects.get(seccion__nombre="Almacén", nombre="Bebidas")
        self.pechuga = self.crear("Pechuga", pollo, "KG", "6500.00", "4000.00", codigo="101", stock="10")
        self.agua = self.crear("Agua 2 L", bebidas, "UNIDAD", "1500.00", "900.00", barras="7790895000997", stock="24")
        self.entrar_como(Rol.EMPLEADO)

    def entrar_como(self, rol):
        datos = {"nombre_usuario": self.usuarios[rol].nombre_usuario, "password": PASSWORD}
        token = self.client.post("/api/auth/login/", datos).data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def crear(self, nombre, categoria, unidad, venta, costo, codigo="", barras="", stock=None):
        r = self.client.post("/api/productos/", {
            "nombre": nombre, "categoria": categoria.id, "unidad": unidad, "precio_venta": venta,
            "precio_costo": costo, "codigo": codigo, "codigo_barras": barras,
        })
        self.assertEqual(r.status_code, 201, r.data)
        if stock:
            self.client.post(f"/api/productos/{r.data['id']}/ingreso/", {"cantidad": stock})
        return Producto.objects.get(pk=r.data["id"])

    def vender(self, items=None, medio="EFECTIVO", **extra):
        items = items if items is not None else [{"producto": self.agua.id, "cantidad": "2"}, {"producto": self.pechuga.id, "cantidad": "1.250"}]
        return self.client.post("/api/ventas/", {"items": items, "medio_pago": medio, **extra}, format="json")


class CodigoDeBarrasTests(Base):
    def test_producto_con_numero_y_codigo_de_barras(self):
        self.entrar_como(Rol.ENCARGADO)
        r = self.client.patch(f"/api/productos/{self.agua.id}/", {"codigo": "205"})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual((r.data["codigo"], r.data["codigo_barras"]), ("205", "7790895000997"))

    def test_se_encuentra_escaneando_o_por_numero(self):
        self.assertEqual(self.client.get("/api/productos/?q=7790895000997").data[0]["nombre"], "Agua 2 L")
        self.assertEqual(self.client.get("/api/productos/?q=101").data[0]["nombre"], "Pechuga")

    def test_un_codigo_no_puede_identificar_a_dos_productos(self):
        self.entrar_como(Rol.ENCARGADO)
        # Ni repetido en el mismo campo, ni cruzado entre número y código de barras
        self.assertIn("codigo_barras", self.client.patch(f"/api/productos/{self.pechuga.id}/", {"codigo_barras": "7790895000997"}).data)
        self.assertIn("codigo", self.client.patch(f"/api/productos/{self.pechuga.id}/", {"codigo": "7790895000997"}).data)
        self.assertIn("codigo_barras", self.client.patch(f"/api/productos/{self.agua.id}/", {"codigo_barras": "101"}).data)
        self.assertIn("codigo", self.client.patch(f"/api/productos/{self.agua.id}/", {"codigo": "7790895000997"}).data)


class VenderTests(Base):
    def test_venta_calcula_total_descuenta_stock_y_queda_a_nombre_del_vendedor(self):  # RF-39, RF-40
        r = self.vender(paga_con="12000")
        self.assertEqual(r.status_code, 201, r.data)
        # 2 × 1500 + 1,25 kg × 6500 = 3000 + 8125
        self.assertEqual(Decimal(r.data["total"]), Decimal("11125.00"))
        self.assertEqual(Decimal(r.data["vuelto"]), Decimal("875.00"))
        self.assertEqual(r.data["vendedor"], "Empleado Test")
        self.assertEqual(r.data["numero"], f"{r.data['id']:06d}")
        self.assertEqual([i["nombre"] for i in r.data["items"]], ["Agua 2 L", "Pechuga"])  # como se cargaron
        self.assertNotIn("costo_unitario", r.data["items"][0])  # el empleado no ve costos
        self.assertEqual(r.data["avisos"], [])

        venta = Venta.objects.get(pk=r.data["id"])
        self.assertEqual(venta.turno.usuario, self.usuarios[Rol.EMPLEADO])
        self.agua.refresh_from_db()
        self.pechuga.refresh_from_db()
        self.assertEqual((self.agua.stock_actual, self.pechuga.stock_actual), (Decimal("22"), Decimal("8.75")))
        m = MovimientoStock.objects.get(producto=self.agua, tipo="VENTA")
        self.assertEqual((m.cantidad, m.stock_resultante), (Decimal("-2"), Decimal("22")))
        self.assertIn(r.data["numero"], m.motivo)

    def test_el_precio_lo_pone_el_sistema_no_la_pantalla(self):
        r = self.vender([{"producto": self.agua.id, "cantidad": "1", "precio_unitario": "1"}])
        self.assertEqual(Decimal(r.data["total"]), Decimal("1500.00"))

    def test_renglones_repetidos_se_suman(self):
        r = self.vender([{"producto": self.agua.id, "cantidad": "1"}, {"producto": self.agua.id, "cantidad": "2"}])
        self.assertEqual(len(r.data["items"]), 1)
        self.assertEqual(Decimal(r.data["items"][0]["cantidad"]), Decimal("3"))

    def test_sin_stock_vende_igual_y_avisa(self):
        r = self.vender([{"producto": self.agua.id, "cantidad": "30"}], medio="QR")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(len(r.data["avisos"]), 1)
        self.assertIn("recuento", r.data["avisos"][0])
        self.agua.refresh_from_db()
        self.assertEqual((self.agua.stock_actual, self.agua.semaforo), (Decimal("-6"), "ROJO"))

    def test_ventas_invalidas(self):
        casos = [
            self.vender([]),
            self.vender([{"producto": 99999, "cantidad": "1"}]),
            self.vender([{"producto": self.agua.id, "cantidad": "0"}]),
            self.vender([{"producto": self.agua.id, "cantidad": "1.5"}]),  # por unidad: entero
            self.vender(medio="CHEQUE"),
            self.vender(paga_con="100"),  # paga con menos que el total
        ]
        for r in casos:
            self.assertEqual(r.status_code, 400, r.data)
        self.assertEqual(Venta.objects.count(), 0)
        self.assertEqual(MovimientoStock.objects.filter(tipo="VENTA").count(), 0)

    def test_producto_dado_de_baja_no_se_vende(self):  # RN-10
        Producto.objects.filter(pk=self.agua.pk).update(activo=False)
        self.assertEqual(self.vender().status_code, 400)

    def test_paga_con_solo_cuenta_en_efectivo(self):
        r = self.vender(medio="DEBITO", paga_con="100")
        self.assertEqual(r.status_code, 201)
        self.assertIsNone(r.data["paga_con"])


class RecibosTests(Base):
    def test_empleado_ve_solo_sus_recibos(self):
        mia = self.vender().data["id"]
        self.entrar_como(Rol.ENCARGADO)
        otra = self.vender().data["id"]
        self.assertEqual({v["id"] for v in self.client.get("/api/ventas/").data}, {mia, otra})
        self.entrar_como(Rol.EMPLEADO)
        self.assertEqual([v["id"] for v in self.client.get("/api/ventas/").data], [mia])
        self.assertEqual(self.client.get(f"/api/ventas/{mia}/").status_code, 200)
        self.assertEqual(self.client.get(f"/api/ventas/{otra}/").status_code, 404)

    def test_recibo_conserva_nombre_y_precio_aunque_cambie_el_producto(self):  # RN-11
        venta = self.vender([{"producto": self.agua.id, "cantidad": "1"}]).data["id"]
        Producto.objects.filter(pk=self.agua.pk).update(nombre="Agua mineral 2 L", precio_venta=Decimal("2000"))
        item = self.client.get(f"/api/ventas/{venta}/").data["items"][0]
        self.assertEqual((item["nombre"], Decimal(item["precio_unitario"])), ("Agua 2 L", Decimal("1500.00")))

    def test_filtro_por_fecha(self):
        self.vender()
        hoy = timezone.localdate()
        self.assertEqual(len(self.client.get(f"/api/ventas/?desde={hoy}&hasta={hoy}").data), 1)
        self.assertEqual(len(self.client.get("/api/ventas/?hasta=2020-01-01").data), 0)
        self.assertEqual(self.client.get("/api/ventas/?desde=ayer").status_code, 400)

    def test_limpieza_del_buzon_los_domingos(self):
        """Cada domingo salen del buzón los recibos de más de una semana. La venta no se borra."""
        ids = {}
        # Un miércoles: 2026-11-11. Domingos: 8/11 y 1/11.
        for nombre, dia in (("hoy", date(2026, 11, 11)), ("semana_pasada", date(2026, 11, 3)), ("vieja", date(2026, 10, 30))):
            ids[nombre] = self.vender([{"producto": self.agua.id, "cantidad": "1"}]).data["id"]
            Venta.objects.filter(pk=ids[nombre]).update(fecha_hora=servicios.inicio_del_dia(dia) + timedelta(hours=10))

        servicios.limpiar_buzon(date(2026, 11, 11))  # corte: domingo 1/11
        en_buzon = dict(Venta.objects.values_list("pk", "en_buzon"))
        self.assertEqual((en_buzon[ids["hoy"]], en_buzon[ids["semana_pasada"]], en_buzon[ids["vieja"]]), (True, True, False))
        self.assertEqual(Venta.objects.count(), 3)  # no se borró nada

        # El sábado 14/11 no cambia nada; el domingo 15/11 sale la de la semana pasada
        servicios.limpiar_buzon(date(2026, 11, 14))
        self.assertTrue(Venta.objects.get(pk=ids["semana_pasada"]).en_buzon)
        servicios.limpiar_buzon(date(2026, 11, 15))
        self.assertFalse(Venta.objects.get(pk=ids["semana_pasada"]).en_buzon)
        self.assertTrue(Venta.objects.get(pk=ids["hoy"]).en_buzon)

        # Fuera del buzón: no aparece en la lista, salvo para un dueño que pide todas
        self.entrar_como(Rol.ADMINISTRADOR)
        self.assertEqual([v["id"] for v in self.client.get("/api/ventas/").data], [ids["hoy"]])
        self.assertEqual(len(self.client.get("/api/ventas/?todas=1").data), 3)
        self.entrar_como(Rol.ENCARGADO)
        self.assertEqual(len(self.client.get("/api/ventas/?todas=1").data), 1)


class AnularTests(Base):
    def setUp(self):
        super().setUp()
        self.venta = self.vender().data["id"]

    def test_empleado_no_anula(self):
        self.assertEqual(self.client.post(f"/api/ventas/{self.venta}/anular/", {"motivo": "x"}).status_code, 403)

    def test_anular_devuelve_el_stock_y_queda_registrado(self):
        self.entrar_como(Rol.ENCARGADO)
        self.assertEqual(self.client.post(f"/api/ventas/{self.venta}/anular/", {}).status_code, 400)  # sin motivo
        r = self.client.post(f"/api/ventas/{self.venta}/anular/", {"motivo": "Se cobró dos veces"})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data["anulada"])
        self.assertEqual((r.data["anulada_por"], r.data["motivo_anulacion"]), ("Encargado Test", "Se cobró dos veces"))
        self.agua.refresh_from_db()
        self.pechuga.refresh_from_db()
        self.assertEqual((self.agua.stock_actual, self.pechuga.stock_actual), (Decimal("24"), Decimal("10")))
        self.assertEqual(self.client.post(f"/api/ventas/{self.venta}/anular/", {"motivo": "otra vez"}).status_code, 400)
        self.assertTrue(Venta.objects.filter(pk=self.venta).exists())  # no se borra


class DineroEnResumenYCierreTests(Base):
    def setUp(self):
        super().setUp()
        self.vender(paga_con="12000")  # 11125 en efectivo
        self.vender([{"producto": self.agua.id, "cantidad": "4"}], medio="QR")  # 6000 por QR
        anulada = self.vender([{"producto": self.agua.id, "cantidad": "1"}]).data["id"]
        self.entrar_como(Rol.ENCARGADO)
        self.client.post(f"/api/ventas/{anulada}/anular/", {"motivo": "Error"})

    def test_vendido_hoy(self):  # RF-41
        r = self.client.get("/api/ventas/hoy/")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual((r.data["cantidad"], r.data["anuladas"]), (2, 1))
        self.assertEqual(Decimal(r.data["total"]), Decimal("17125.00"))
        self.assertEqual(Decimal(r.data["efectivo"]), Decimal("11125.00"))
        # Costo: 6 aguas × 900 + 1,25 kg × 4000 = 10400
        self.assertEqual(Decimal(r.data["ganancia_bruta"]), Decimal("6725.00"))
        self.assertEqual({m["medio"]: Decimal(m["total"]) for m in r.data["por_medio"]},
                         {"EFECTIVO": Decimal("11125.00"), "QR": Decimal("6000.00")})
        self.assertEqual({s["seccion"]: Decimal(s["total"]) for s in r.data["por_seccion"]},
                         {"Almacén": Decimal("9000.00"), "Carnicería": Decimal("8125.00")})
        self.entrar_como(Rol.EMPLEADO)
        self.assertEqual(self.client.get("/api/ventas/hoy/").status_code, 403)

    def test_resumen_actividad_y_cierre_incluyen_las_ventas(self):
        self.entrar_como(Rol.ADMINISTRADOR)
        dia = servicios.fecha_local(Venta.objects.first().fecha_hora)
        r = self.client.get(f"/api/resumen/?desde={dia}&hasta={dia}").data
        self.assertEqual(Decimal(r["ventas"]["total"]), Decimal("17125.00"))
        self.assertEqual(Decimal(r["por_dia"][0]["vendido"]), Decimal("17125.00"))
        agua = next(p for p in r["mercaderia"]["por_producto"] if p["nombre"] == "Agua 2 L")
        self.assertEqual(Decimal(agua["vendido"]), Decimal("6"))  # la anulada no cuenta

        ahora = timezone.now()
        a = self.client.get("/api/actividad/", {"desde": (ahora - timedelta(hours=1)).isoformat(),
                                                "hasta": (ahora + timedelta(hours=1)).isoformat(), "grupo": "VENTAS"}).data
        self.assertEqual(sorted(e["titulo"] for e in a["eventos"]), ["Anulación de venta", "Venta", "Venta", "Venta"])

        servicios.generar_cierre(dia)
        cierre = CierreDiario.objects.get(fecha=dia)
        self.assertEqual((cierre.ventas_cantidad, cierre.ventas_total, cierre.ventas_efectivo, cierre.ganancia_bruta),
                         (2, Decimal("17125.00"), Decimal("11125.00"), Decimal("6725.00")))
        self.assertEqual(CierreDiario.objects.count(), 1)


class ModificarCompraPagadaTests(Base):
    """El cliente pagó y después quiere agregar, sacar o cambiar algo (RF-86 a RF-88)."""

    def setUp(self):
        super().setUp()
        self.original = self.vender(paga_con="12000").data  # 2 aguas + 1,25 kg de pechuga = 11125

    def corregir(self, items, medio="EFECTIVO", venta=None):
        return self.client.post(f"/api/ventas/{venta or self.original['id']}/corregir/",
                                {"items": items, "medio_pago": medio}, format="json")

    def test_agregar_un_producto_olvidado(self):
        r = self.corregir([{"producto": self.agua.id, "cantidad": "3"}, {"producto": self.pechuga.id, "cantidad": "1.250"}])
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(Decimal(r.data["total"]), Decimal("12625.00"))  # una agua más: +1500
        self.assertEqual(r.data["corrige_a"], {"id": self.original["id"], "numero": self.original["numero"], "total": "11125.00",
                                               "medio_pago": "EFECTIVO"})
        self.assertNotEqual(r.data["numero"], self.original["numero"])

        vieja = Venta.objects.get(pk=self.original["id"])  # no se borra: queda como reemplazada
        self.assertTrue(vieja.anulada)
        self.assertEqual(vieja.anulada_por, self.usuarios[Rol.EMPLEADO])
        self.assertIn(r.data["numero"], vieja.motivo_anulacion)
        self.assertEqual(self.client.get(f"/api/ventas/{vieja.pk}/").data["reemplazada_por"]["numero"], r.data["numero"])

        self.agua.refresh_from_db()
        self.pechuga.refresh_from_db()
        self.assertEqual((self.agua.stock_actual, self.pechuga.stock_actual), (Decimal("21"), Decimal("8.75")))

    def test_sacar_un_producto_devuelve_su_stock(self):
        r = self.corregir([{"producto": self.agua.id, "cantidad": "2"}])
        self.assertEqual(Decimal(r.data["total"]), Decimal("3000.00"))
        self.pechuga.refresh_from_db()
        self.assertEqual(self.pechuga.stock_actual, Decimal("10"))
        self.assertEqual(r.data["avisos"], [])

    def test_cambiar_solo_el_medio_de_pago(self):
        r = self.corregir(self.original_items(), medio="QR")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual((r.data["medio_pago"], Decimal(r.data["total"])), ("QR", Decimal("11125.00")))

    def original_items(self):
        return [{"producto": i["producto"], "cantidad": i["cantidad"]} for i in self.original["items"]]

    def test_sin_cambios_no_hace_nada(self):
        r = self.corregir(self.original_items())
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Venta.objects.get(pk=self.original["id"]).anulada)
        self.assertEqual(Venta.objects.count(), 1)

    def test_si_la_correccion_es_invalida_no_cambia_nada(self):
        self.assertEqual(self.corregir([]).status_code, 400)
        self.assertEqual(self.corregir([{"producto": self.agua.id, "cantidad": "1.5"}]).status_code, 400)
        self.assertFalse(Venta.objects.get(pk=self.original["id"]).anulada)
        self.agua.refresh_from_db()
        self.assertEqual(self.agua.stock_actual, Decimal("22"))  # como quedó después de la venta original

    def test_se_puede_corregir_mas_de_una_vez_pero_no_el_recibo_viejo(self):
        segunda = self.corregir([{"producto": self.agua.id, "cantidad": "1"}]).data
        self.assertEqual(self.corregir([{"producto": self.agua.id, "cantidad": "5"}]).status_code, 400)  # el viejo ya no
        tercera = self.corregir([{"producto": self.agua.id, "cantidad": "5"}], venta=segunda["id"])
        self.assertEqual(tercera.status_code, 201, tercera.data)
        self.agua.refresh_from_db()
        self.assertEqual(self.agua.stock_actual, Decimal("19"))

    def test_quien_puede_modificar(self):
        self.assertTrue(self.client.get(f"/api/ventas/{self.original['id']}/").data["puede_corregir"])
        # Una venta suya de otro día: el cajero ya no puede, el encargado sí
        Venta.objects.filter(pk=self.original["id"]).update(fecha_hora=timezone.now() - timedelta(days=1))
        self.assertFalse(self.client.get(f"/api/ventas/{self.original['id']}/").data["puede_corregir"])
        self.assertEqual(self.corregir([{"producto": self.agua.id, "cantidad": "1"}]).status_code, 400)
        self.entrar_como(Rol.ENCARGADO)
        ajena_del_encargado = self.vender([{"producto": self.agua.id, "cantidad": "1"}]).data["id"]
        self.assertEqual(self.corregir([{"producto": self.agua.id, "cantidad": "1"}]).status_code, 201)
        # Un cajero no puede tocar la venta de otro (ni saber que existe)
        self.entrar_como(Rol.EMPLEADO)
        self.assertEqual(self.corregir([{"producto": self.agua.id, "cantidad": "2"}], venta=ajena_del_encargado).status_code, 404)

    def test_en_los_totales_cuenta_solo_la_version_corregida(self):
        self.corregir([{"producto": self.agua.id, "cantidad": "2"}])  # queda en 3000
        self.entrar_como(Rol.ADMINISTRADOR)
        hoy = self.client.get("/api/ventas/hoy/").data
        self.assertEqual((hoy["cantidad"], hoy["anuladas"], hoy["modificadas"]), (1, 0, 1))
        self.assertEqual(Decimal(hoy["total"]), Decimal("3000.00"))
        ahora = timezone.now()
        a = self.client.get("/api/actividad/", {"desde": (ahora - timedelta(hours=1)).isoformat(),
                                                "hasta": (ahora + timedelta(hours=1)).isoformat(), "grupo": "VENTAS"}).data
        self.assertEqual(sorted(e["titulo"] for e in a["eventos"]), ["Compra modificada", "Venta"])
        modificada = next(e for e in a["eventos"] if e["titulo"] == "Compra modificada")
        self.assertIn("$11125.00 → $3000.00", modificada["detalle"])
        self.assertEqual(modificada["quien"]["nombre"], "Empleado Test")
