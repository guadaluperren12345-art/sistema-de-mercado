"""Pruebas de compras a comerciantes (RF-112 a RF-119) y de resultados por sección (RF-51 a RF-54).

Ejecutar con:  docker compose exec backend python manage.py test compras
"""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APITestCase

from core import dia

from productos.models import Categoria, MovimientoStock, Producto
from turnos import servicios as turnos
from usuarios.models import Rol, Usuario

from .models import Comerciante, Compra, PagoCompra

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
        self.pechuga = self.producto("Pechuga", pollo, "KG", "6500.00", "4000.00")
        self.agua = self.producto("Agua 2 L", bebidas, "UNIDAD", "1500.00", "900.00")

    def entrar_como(self, rol):
        datos = {"nombre_usuario": self.usuarios[rol].nombre_usuario, "password": PASSWORD}
        token = self.client.post("/api/auth/login/", datos).data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def producto(self, nombre, categoria, unidad, venta, costo):
        r = self.client.post("/api/productos/", {"nombre": nombre, "categoria": categoria.id, "unidad": unidad,
                                                 "precio_venta": venta, "precio_costo": costo})
        self.assertEqual(r.status_code, 201, r.data)
        return Producto.objects.get(pk=r.data["id"])

    def comprar(self, **cambios):
        datos = {"comerciante": "granja san josé", "producto": self.pechuga.id, "cantidad": "20",
                 "costo_total": "80000", **cambios}
        return self.client.post("/api/compras/", datos, format="json")

    def stock(self, producto):
        return Producto.objects.get(pk=producto.id).stock_actual


class ComprasTests(Base):
    def test_compra_sin_pagar(self):  # RF-113, rojo
        r = self.comprar()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["comerciante_nombre"], "Granja san josé")
        self.assertEqual((r.data["nombre_producto"], r.data["cantidad"], r.data["costo_total"]), ("Pechuga", "20.000", "80000.00"))
        self.assertEqual(r.data["costo_unitario"], "4000.00")
        self.assertEqual((r.data["estado"], r.data["pagado"], r.data["falta"]), ("DEBE", "0.00", "80000.00"))
        self.assertEqual(r.data["usuario"], "Encargado Test")
        self.assertIsNotNone(r.data["fecha_hora"])  # la pone el sistema
        self.assertEqual(r.data["pagos"], [])

    def test_compra_pagada_y_pagada_en_parte(self):  # verde y amarillo
        pagada = self.comprar(pagado="80000", medio_pago="TRANSFERENCIA").data
        self.assertEqual((pagada["estado"], pagada["falta"]), ("PAGADO", "0.00"))
        self.assertEqual(pagada["pagos"][0]["medio_pago_texto"], "Transferencia")
        parcial = self.comprar(pagado="30000").data
        self.assertEqual((parcial["estado"], parcial["pagado"], parcial["falta"]), ("PARCIAL", "30000.00", "50000.00"))

    def test_la_compra_suma_al_stock(self):  # RF-114
        self.comprar()
        self.assertEqual(self.stock(self.pechuga), Decimal("20.000"))
        m = MovimientoStock.objects.get(producto=self.pechuga)
        self.assertEqual((m.tipo, m.cantidad, m.costo_unitario), ("INGRESO", Decimal("20.000"), Decimal("4000.00")))
        self.assertIn("Granja san josé", m.motivo)
        self.comprar(sumar_stock=False)  # ya estaba cargada en Stock
        self.assertEqual(self.stock(self.pechuga), Decimal("20.000"))

    def test_compra_por_cajon(self):  # RF-120: no hace falta contar una por una
        r = self.comprar(cantidad=None, presentacion="CAJON", bultos="2", contenido="18", costo_total="72000")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual((r.data["presentacion"], r.data["bultos"], r.data["contenido"]), ("CAJON", "2.000", "18.000"))
        self.assertEqual(r.data["presentacion_texto"], "2 cajones × 18 kg")
        self.assertEqual((r.data["cantidad"], r.data["costo_bulto"], r.data["costo_unitario"]), ("36.000", "36000.00", "2000.00"))
        self.assertEqual(self.stock(self.pechuga), Decimal("36.000"))  # el stock sigue en kilos
        self.assertIn("2 cajones × 18 kg", MovimientoStock.objects.get(producto=self.pechuga).motivo)
        una = self.comprar(cantidad=None, presentacion="BOLSA", bultos="1", contenido="10").data
        self.assertEqual(una["presentacion_texto"], "1 bolsa × 10 kg")

    def test_usa_lo_que_trae_el_cajon_cargado_en_el_producto(self):
        self.client.patch(f"/api/productos/{self.agua.id}/", {"presentacion": "PACK", "contenido": "6"})
        r = self.comprar(producto=self.agua.id, cantidad=None, presentacion="PACK", bultos="4", costo_total="21600")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual((r.data["presentacion_texto"], r.data["cantidad"], r.data["costo_bulto"]), ("4 packs × 6 u.", "24.000", "5400.00"))
        self.assertEqual(self.stock(self.agua), Decimal("24.000"))

    def test_validaciones_por_bulto(self):
        self.assertIn("bultos", self.comprar(cantidad=None, presentacion="CAJON", contenido="18").data)
        self.assertIn("bultos", self.comprar(cantidad=None, presentacion="CAJON", bultos="0", contenido="18").data)
        self.assertIn("contenido", self.comprar(cantidad=None, presentacion="CAJON", bultos="2").data)  # no se sabe cuánto trae
        self.assertIn("presentacion", self.comprar(presentacion="TACHO").data)
        self.assertIn("contenido", self.comprar(producto=self.agua.id, cantidad=None, presentacion="CAJA", bultos="2", contenido="6.5").data)
        self.assertIn("cantidad", self.comprar(cantidad=None).data)  # suelto necesita la cantidad
        self.assertFalse(Compra.objects.exists())
        suelto = self.comprar(bultos="5", contenido="3").data  # suelto: lo de las cajas se ignora
        self.assertEqual((suelto["cantidad"], suelto["bultos"], suelto["presentacion_texto"]), ("20.000", None, None))

    def test_comprar_algo_que_no_existia_lo_crea_como_producto(self):  # RF-122
        verduras = Categoria.objects.get(seccion__nombre="Verdulería", nombre="Verduras")
        nuevo = {"nombre": "cebolla", "categoria": verduras.id, "unidad": "KG", "precio_venta": "1800"}
        r = self.comprar(producto=None, producto_nuevo=nuevo, cantidad=None, presentacion="CAJON", bultos="1",
                         contenido="20", costo_total="20000")
        self.assertEqual(r.status_code, 201, r.data)
        cebolla = Producto.objects.get(nombre="Cebolla")
        self.assertEqual(r.data["producto"], cebolla.id)
        self.assertEqual((cebolla.precio_venta, cebolla.precio_costo), (Decimal("1800.00"), Decimal("1000.00")))  # 20.000 / 20 kg
        self.assertEqual((cebolla.stock_actual, cebolla.presentacion_texto), (Decimal("20.000"), "Cajón de 20 kg"))
        self.assertEqual(cebolla.creado_por, self.usuarios[Rol.ENCARGADO])
        # Aparece en Productos y en Stock como cualquier otro
        nombres = [p["nombre"] for p in self.client.get("/api/productos/?activo=1").data]
        self.assertIn("Cebolla", nombres)
        from productos.models import CambioProducto
        self.assertIn("creado al anotar una compra", CambioProducto.objects.get(producto=cebolla, accion="ALTA").detalle)

    def test_producto_nuevo_con_datos_malos_no_guarda_nada(self):
        verduras = Categoria.objects.get(seccion__nombre="Verdulería", nombre="Verduras")
        base = {"nombre": "Cebolla", "categoria": verduras.id, "unidad": "KG", "precio_venta": "1800"}
        for cambio in ({"precio_venta": "0"}, {"nombre": ""}, {"categoria": 99999}, {"unidad": "LITRO"}):
            r = self.comprar(producto=None, producto_nuevo={**base, **cambio})
            self.assertEqual(r.status_code, 400)
            self.assertIn("producto_nuevo", r.data)
        pollo = Categoria.objects.get(seccion__nombre="Carnicería", nombre="Pollo")
        repetido = self.comprar(producto=None, producto_nuevo={**base, "nombre": "PECHUGA", "categoria": pollo.id})
        self.assertIn("nombre", repetido.data["producto_nuevo"])  # ya existe en esa sección
        self.assertIn("producto", self.comprar(producto=None).data)  # ni producto ni datos para crearlo
        self.assertFalse(Producto.objects.filter(nombre="Cebolla").exists())
        self.assertFalse(Compra.objects.exists())

    def test_el_comerciante_no_se_duplica(self):
        self.comprar()
        self.comprar(comerciante="  GRANJA   SAN JOSÉ ")
        self.comprar(comerciante="Distribuidora Sur", producto=self.agua.id, cantidad="24", costo_total="21600")
        self.assertEqual(Comerciante.objects.count(), 2)

    def test_validaciones(self):
        self.assertIn("comerciante", self.comprar(comerciante=" ").data)
        self.assertIn("producto", self.comprar(producto=99999).data)
        self.assertIn("cantidad", self.comprar(cantidad="0").data)
        self.assertIn("cantidad", self.comprar(producto=self.agua.id, cantidad="2.5").data)  # va por unidad
        self.assertIn("costo_total", self.comprar(costo_total="0").data)
        self.assertIn("pagado", self.comprar(pagado="80000.01").data)
        self.client.post(f"/api/productos/{self.agua.id}/desactivar/")
        self.assertIn("producto", self.comprar(producto=self.agua.id, cantidad="1").data)
        self.assertFalse(Compra.objects.exists())

    def test_solo_duenos_y_encargados(self):  # RF-112
        compra = self.comprar().data["id"]
        self.entrar_como(Rol.EMPLEADO)
        self.assertEqual(self.comprar().status_code, 403)
        self.assertEqual(self.client.get("/api/compras/").status_code, 403)
        self.assertEqual(self.client.post(f"/api/compras/{compra}/pago/", {"importe": "100"}, format="json").status_code, 403)
        self.assertEqual(self.client.post(f"/api/compras/{compra}/anular/", {"motivo": "x"}).status_code, 403)
        self.entrar_como(Rol.ADMINISTRADOR)
        self.assertEqual(self.comprar().status_code, 201)

    def test_pagar_despues(self):  # RF-116: de rojo a amarillo y a verde
        compra = self.comprar().data["id"]
        r = self.client.post(f"/api/compras/{compra}/pago/", {"importe": "30000"}, format="json")
        self.assertEqual((r.status_code, r.data["estado"], r.data["falta"]), (200, "PARCIAL", "50000.00"))
        self.assertEqual(self.client.post(f"/api/compras/{compra}/pago/", {"importe": "50000.01"}, format="json").status_code, 400)
        r = self.client.post(f"/api/compras/{compra}/pago/", {"importe": "50000", "medio_pago": "TRANSFERENCIA"}, format="json")
        self.assertEqual((r.data["estado"], r.data["falta"], len(r.data["pagos"])), ("PAGADO", "0.00", 2))
        self.assertEqual(self.client.post(f"/api/compras/{compra}/pago/", {"importe": "1"}, format="json").status_code, 400)
        self.assertEqual(self.client.post("/api/compras/99999/pago/", {"importe": "1"}, format="json").status_code, 404)

    def test_lista_filtros_y_deuda(self):  # RF-115, RF-117
        self.comprar()                                                         # debe 80.000
        self.comprar(pagado="30000")                                           # debe 50.000
        self.comprar(comerciante="Distribuidora Sur", producto=self.agua.id, cantidad="24", costo_total="21600", pagado="21600")
        r = self.client.get("/api/compras/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["deuda_total"], "130000.00")
        self.assertEqual([c["estado"] for c in r.data["compras"]], ["PAGADO", "PARCIAL", "DEBE"])  # lo más nuevo primero
        deudas = {c["nombre"]: c["deuda"] for c in r.data["comerciantes"]}
        self.assertEqual(deudas, {"Distribuidora Sur": "0.00", "Granja san josé": "130000.00"})
        for estado in ("DEBE", "PARCIAL", "PAGADO"):
            lista = self.client.get(f"/api/compras/?estado={estado}").data["compras"]
            self.assertEqual([c["estado"] for c in lista], [estado])
        sur = Comerciante.objects.get(nombre="Distribuidora Sur").id
        self.assertEqual(len(self.client.get(f"/api/compras/?comerciante={sur}").data["compras"]), 1)
        self.assertEqual(self.client.get("/api/compras/?desde=ayer").status_code, 400)

    def test_anular(self):
        compra = self.comprar(pagado="30000").data["id"]
        self.assertEqual(self.client.post(f"/api/compras/{compra}/anular/").status_code, 400)  # falta el motivo
        r = self.client.post(f"/api/compras/{compra}/anular/", {"motivo": "Era otra cantidad"})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data["anulada"])
        self.assertEqual(self.stock(self.pechuga), 0)  # la mercadería que había sumado vuelve a salir
        self.assertEqual(self.client.get("/api/compras/").data["deuda_total"], "0.00")
        self.assertEqual(self.client.post(f"/api/compras/{compra}/anular/", {"motivo": "x"}).status_code, 400)
        self.assertEqual(self.client.post(f"/api/compras/{compra}/pago/", {"importe": "1"}, format="json").status_code, 400)

    def test_resumen_cierre_y_actividad(self):  # RF-118, RF-119
        self.comprar(pagado="30000")                                       # efectivo
        otra = self.comprar().data["id"]
        self.client.post(f"/api/compras/{otra}/pago/", {"importe": "10000", "medio_pago": "TRANSFERENCIA"}, format="json")
        anulada = self.comprar(pagado="5000").data["id"]
        self.client.post(f"/api/compras/{anulada}/anular/", {"motivo": "Error"})
        hoy = dia.hoy()
        r = turnos.resumen(hoy, hoy)
        self.assertEqual(r["comerciantes"], {"compras": 2, "comprado": "160000.00", "pagos": 2, "pagado": "40000.00",
                                             "pagado_efectivo": "30000.00", "deuda_actual": "120000.00"})
        self.assertEqual(r["caja"], {"entro": "0.00", "gastos": "0.00", "pagos_comerciantes": "40000.00",
                                     "resultado": "-40000.00", "efectivo": "-30000.00"})
        self.assertEqual(r["mercaderia"]["ingresos"]["valor"], "160000.00")  # la anulada no cuenta
        cierre = turnos.generar_cierre(hoy)[0]
        cierre.refresh_from_db()
        self.assertEqual((cierre.compras_total, cierre.pagos_comerciantes, cierre.pagos_comerciantes_efectivo),
                         (Decimal("160000.00"), Decimal("40000.00"), Decimal("30000.00")))
        self.assertEqual((cierre.resultado_dia, cierre.efectivo_esperado), (Decimal("-40000.00"), Decimal("-30000.00")))
        ahora = timezone.now()
        eventos = turnos.actividad(ahora - timedelta(hours=1), ahora + timedelta(minutes=1), grupo="COMPRAS")["eventos"]
        titulos = [e["titulo"] for e in eventos]
        self.assertEqual((titulos.count("Compra a comerciante"), titulos.count("Pago a comerciante"), titulos.count("Compra anulada")), (3, 3, 1))
        self.assertEqual(PagoCompra.objects.count(), 3)


class ResultadosTests(Base):
    """Resultados por sección: ventas − costo − pérdidas; los gastos solo en el total general."""

    def setUp(self):
        super().setUp()
        self.client.post(f"/api/productos/{self.pechuga.id}/ingreso/", {"cantidad": "50"})
        self.client.post(f"/api/productos/{self.agua.id}/ingreso/", {"cantidad": "48"})

        def vender(producto, cantidad):
            cuerpo = {"items": [{"producto": producto.id, "cantidad": cantidad}], "medio_pago": "EFECTIVO"}
            r = self.client.post("/api/ventas/", cuerpo, format="json")
            self.assertEqual(r.status_code, 201, r.data)
            return r.data["id"]

        vender(self.pechuga, "2")          # Carnicería: vende 13.000, costó 8.000
        vender(self.agua, "10")            # Almacén: vende 15.000, costó 9.000
        anulada = vender(self.agua, "5")   # no cuenta
        self.client.post(f"/api/ventas/{anulada}/anular/", {"motivo": "Se arrepintió"})
        self.client.post(f"/api/productos/{self.pechuga.id}/perdida/", {"cantidad": "1", "motivo": "Se venció"})  # −4.000
        self.client.post("/api/gastos/", {"monto": "2500", "proposito": "Bolsas"}, format="json")
        self.entrar_como(Rol.ADMINISTRADOR)

    def test_resultado_de_cada_seccion_y_general(self):
        hoy = dia.hoy().isoformat()
        r = self.client.get(f"/api/resultados/?desde={hoy}&hasta={hoy}")
        self.assertEqual(r.status_code, 200, r.data)
        secciones = {s["seccion"]: s for s in r.data["secciones"]}
        self.assertEqual(list(secciones), ["Almacén", "Carnicería", "Verdulería"])  # siempre las tres
        carniceria = secciones["Carnicería"]
        self.assertEqual({k: carniceria[k] for k in ("ventas", "costo", "ganancia_bruta", "perdidas", "resultado")},
                         {"ventas": "13000.00", "costo": "8000.00", "ganancia_bruta": "5000.00", "perdidas": "4000.00",
                          "resultado": "1000.00"})
        self.assertEqual(secciones["Almacén"]["resultado"], "6000.00")
        self.assertEqual((secciones["Verdulería"]["resultado"], secciones["Verdulería"]["productos"]), ("0.00", []))
        # Los productos de cada sección
        pechuga = carniceria["productos"][0]
        self.assertEqual((pechuga["nombre"], pechuga["categoria"], pechuga["vendido"], pechuga["perdido"], pechuga["resultado"]),
                         ("Pechuga", "Pollo", "2.000", "1.000", "1000.00"))
        self.assertEqual(secciones["Almacén"]["productos"][0]["vendido"], "10.000")
        # Los gastos se restan una sola vez, en el total general
        self.assertEqual(r.data["general"], {"ventas": "28000.00", "costo": "17000.00", "ganancia_bruta": "11000.00",
                                             "perdidas": "4000.00", "resultado": "4500.00", "gastos": "2500.00",
                                             "resultado_secciones": "7000.00"})
        self.assertEqual(r.data["comparacion"], {"vende_mas": "Almacén", "gana_mas": "Almacén", "pierde_mas": "Carnicería"})

    def test_periodo_sin_movimientos_y_limites(self):
        r = self.client.get("/api/resultados/?desde=2020-01-01&hasta=2020-12-31")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["general"]["resultado"], "0.00")
        self.assertEqual(r.data["comparacion"], {"vende_mas": None, "gana_mas": None, "pierde_mas": None})
        self.assertEqual(self.client.get("/api/resultados/?desde=2020-01-01&hasta=2021-06-01").status_code, 400)
        self.assertEqual(self.client.get("/api/resultados/?desde=mal").status_code, 400)

    def test_solo_duenos(self):
        self.entrar_como(Rol.ENCARGADO)
        self.assertEqual(self.client.get("/api/resultados/").status_code, 403)
