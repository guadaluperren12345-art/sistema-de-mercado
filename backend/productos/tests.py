"""Pruebas de secciones, categorías y productos.

Ejecutar con:  docker compose exec backend python manage.py test productos
"""

from decimal import Decimal

from rest_framework.test import APITestCase

from usuarios.models import Rol, Usuario

from .models import CambioProducto, Categoria, MovimientoStock, Producto, Seccion

PASSWORD = "Mercado2026"


class BaseProductos(APITestCase):
    def setUp(self):
        self.usuarios = {}
        for i, rol in enumerate((Rol.ADMINISTRADOR, Rol.ENCARGADO, Rol.EMPLEADO), start=1):
            self.usuarios[rol] = Usuario.objects.create_user(
                rol.lower(), PASSWORD, nombre=rol, apellido="Test", dni=f"2000000{i}",
                rol=Rol.objects.get(nombre=rol), debe_cambiar_password=False,
            )
        self.pollo = Categoria.objects.get(seccion__nombre="Carnicería", nombre="Pollo")
        self.bebidas = Categoria.objects.get(seccion__nombre="Almacén", nombre="Bebidas")
        self.entrar_como(Rol.ENCARGADO)

    def entrar_como(self, rol):
        datos = {"nombre_usuario": self.usuarios[rol].nombre_usuario, "password": PASSWORD}
        token = self.client.post("/api/auth/login/", datos).data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def alta(self, **cambios):
        datos = {"nombre": "pechuga", "categoria": self.pollo.id, "unidad": "KG",
                 "precio_venta": "6500.00", "precio_costo": "4800.50", "codigo": ""}
        datos.update(cambios)
        return self.client.post("/api/productos/", datos)


class SeccionesTests(BaseProductos):
    def test_tres_secciones_con_categorias(self):  # RF-29
        r = self.client.get("/api/secciones/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual([s["nombre"] for s in r.data], ["Almacén", "Carnicería", "Verdulería"])
        self.assertIn("Pollo", [c["nombre"] for c in r.data[1]["categorias"]])

    def test_crear_categoria(self):
        carniceria = Seccion.objects.get(nombre="Carnicería")
        r = self.client.post("/api/categorias/", {"seccion": carniceria.id, "nombre": "  achuras "})
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["nombre"], "Achuras")

    def test_categoria_repetida_sin_importar_mayusculas(self):
        r = self.client.post("/api/categorias/", {"seccion": self.pollo.seccion_id, "nombre": "POLLO"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("nombre", r.data)

    def test_empleado_no_crea_categorias(self):
        self.entrar_como(Rol.EMPLEADO)
        r = self.client.post("/api/categorias/", {"seccion": self.pollo.seccion_id, "nombre": "Nueva"})
        self.assertEqual(r.status_code, 403)


class AltaProductoTests(BaseProductos):
    def test_alta_correcta(self):  # RF-31
        r = self.alta()
        self.assertEqual(r.status_code, 201, r.data)
        p = Producto.objects.get(pk=r.data["id"])
        self.assertEqual(p.nombre, "Pechuga")
        self.assertIsNone(p.codigo)
        self.assertEqual(str(p.precio_costo), "4800.50")
        self.assertEqual(r.data["seccion"], "Carnicería")
        self.assertEqual(p.creado_por, self.usuarios[Rol.ENCARGADO])
        self.assertTrue(CambioProducto.objects.filter(producto=p, accion="ALTA").exists())

    def test_administrador_tambien_da_de_alta(self):
        self.entrar_como(Rol.ADMINISTRADOR)
        self.assertEqual(self.alta().status_code, 201)

    def test_empleado_no_da_de_alta(self):
        self.entrar_como(Rol.EMPLEADO)
        self.assertEqual(self.alta().status_code, 403)

    def test_varios_productos_sin_codigo(self):
        self.assertEqual(self.alta().status_code, 201)
        self.assertEqual(self.alta(nombre="Muslo").status_code, 201)

    def test_codigo_repetido(self):
        self.alta(nombre="Coca 1,5 L", categoria=self.bebidas.id, unidad="UNIDAD", codigo="7790895000997")
        r = self.alta(nombre="Otra", categoria=self.bebidas.id, unidad="UNIDAD", codigo="7790895000997")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Coca", str(r.data["codigo"]))

    def test_nombre_repetido_en_la_seccion(self):
        self.alta()
        r = self.alta(nombre="PECHUGA")
        self.assertEqual(r.status_code, 400)
        self.assertIn("nombre", r.data)
        # En otra sección sí se puede
        self.assertEqual(self.alta(categoria=self.bebidas.id).status_code, 201)

    def test_datos_invalidos(self):
        self.assertIn("precio_venta", self.alta(precio_venta="0").data)
        self.assertIn("precio_costo", self.alta(precio_costo="-1").data)
        self.assertIn("unidad", self.alta(unidad="LITRO").data)
        self.assertIn("codigo", self.alta(codigo="12 34").data)
        self.assertIn("categoria", self.alta(categoria=9999).data)
        self.assertEqual(Producto.objects.count(), 0)


class ListaProductosTests(BaseProductos):
    def setUp(self):
        super().setUp()
        self.alta()
        self.alta(nombre="Agua 2 L", categoria=self.bebidas.id, unidad="UNIDAD", codigo="779001")

    def test_filtros(self):
        self.assertEqual(len(self.client.get("/api/productos/").data), 2)
        carniceria = self.pollo.seccion_id
        self.assertEqual(len(self.client.get(f"/api/productos/?seccion={carniceria}").data), 1)
        self.assertEqual(self.client.get("/api/productos/?q=agua").data[0]["codigo"], "779001")
        self.assertEqual(self.client.get("/api/productos/?q=779001").data[0]["nombre"], "Agua 2 L")

    def test_empleado_ve_productos_sin_costo(self):
        self.entrar_como(Rol.EMPLEADO)
        r = self.client.get("/api/productos/")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("precio_costo", r.data[0])
        self.assertIn("precio_venta", r.data[0])

    def test_encargado_ve_costo(self):
        self.assertIn("precio_costo", self.client.get("/api/productos/").data[0])


class EditarProductoTests(BaseProductos):
    """Corrección de nombre, código, categoría y unidad."""

    def setUp(self):
        super().setUp()
        self.id = self.alta(nombre="Pechga", codigo="101").data["id"]

    def editar(self, **datos):
        return self.client.patch(f"/api/productos/{self.id}/", datos)

    def test_corregir_nombre(self):
        r = self.editar(nombre="pechuga")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["nombre"], "Pechuga")
        cambio = CambioProducto.objects.get(producto_id=self.id, accion="EDICION")
        self.assertEqual(cambio.detalle, "Nombre: Pechga → Pechuga")
        self.assertEqual(cambio.realizado_por, self.usuarios[Rol.ENCARGADO])

    def test_cambiar_categoria_codigo_y_unidad(self):
        vacuno = Categoria.objects.get(seccion__nombre="Carnicería", nombre="Vacuno")
        r = self.editar(categoria=vacuno.id, codigo="", unidad="UNIDAD")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertIsNone(r.data["codigo"])
        self.assertEqual(r.data["categoria_nombre"], "Vacuno")
        detalle = CambioProducto.objects.get(producto_id=self.id, accion="EDICION").detalle
        self.assertIn("Número: 101 → —", detalle)
        self.assertIn("Unidad: Por kilo → Por unidad", detalle)

    def test_mismo_nombre_y_codigo_propios_no_dan_error(self):
        self.assertEqual(self.editar(nombre="Pechga", codigo="101").status_code, 200)
        self.assertFalse(CambioProducto.objects.filter(producto_id=self.id, accion="EDICION").exists())

    def test_no_repetir_nombre_ni_codigo_de_otro(self):
        self.alta(nombre="Muslo", codigo="102")
        self.assertIn("nombre", self.editar(nombre="muslo").data)
        self.assertIn("codigo", self.editar(codigo="102").data)

    def test_precios_no_se_cambian_al_editar(self):
        r = self.editar(nombre="Pechuga", precio_venta="1.00", precio_costo="1.00")
        self.assertEqual(r.status_code, 200)
        p = Producto.objects.get(pk=self.id)
        self.assertEqual(str(p.precio_venta), "6500.00")
        self.assertEqual(str(p.precio_costo), "4800.50")

    def test_empleado_no_edita(self):
        self.entrar_como(Rol.EMPLEADO)
        self.assertEqual(self.editar(nombre="Pechuga").status_code, 403)

    def test_put_no_permitido(self):
        self.assertEqual(self.client.put(f"/api/productos/{self.id}/", {"nombre": "X"}).status_code, 405)


class BajaProductoTests(BaseProductos):
    def setUp(self):
        super().setUp()
        self.id = self.alta().data["id"]

    def test_baja_y_reactivacion(self):  # RF-33, RN-10
        r = self.client.post(f"/api/productos/{self.id}/desactivar/", {"motivo": "No se vende más"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["activo"])
        self.assertTrue(Producto.objects.filter(pk=self.id).exists())  # no se borra
        self.assertEqual(len(self.client.get("/api/productos/?activo=1").data), 0)
        self.assertEqual(len(self.client.get("/api/productos/?activo=0").data), 1)
        self.assertTrue(CambioProducto.objects.filter(producto_id=self.id, accion="BAJA", detalle="No se vende más").exists())

        r = self.client.post(f"/api/productos/{self.id}/reactivar/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["activo"])

    def test_no_repetir_baja_ni_reactivacion(self):
        self.assertEqual(self.client.post(f"/api/productos/{self.id}/reactivar/").status_code, 400)
        self.client.post(f"/api/productos/{self.id}/desactivar/")
        self.assertEqual(self.client.post(f"/api/productos/{self.id}/desactivar/").status_code, 400)

    def test_empleado_no_da_de_baja(self):
        self.entrar_como(Rol.EMPLEADO)
        self.assertEqual(self.client.post(f"/api/productos/{self.id}/desactivar/").status_code, 403)

    def test_producto_dado_de_baja_avisa_al_cargarlo_de_nuevo(self):
        self.client.post(f"/api/productos/{self.id}/desactivar/")
        r = self.alta()
        self.assertEqual(r.status_code, 400)
        self.assertIn("reactivarlo", str(r.data["nombre"]))


class StockTests(BaseProductos):
    """Stock exacto con movimientos, pérdidas, recuento y semáforo (RF-34 a RF-38, RN-09)."""

    def setUp(self):
        super().setUp()
        self.id = self.alta().data["id"]  # pechuga, por kilo, costo 4800,50
        self.agua = self.alta(nombre="Agua 2 L", categoria=self.bebidas.id, unidad="UNIDAD",
                              precio_venta="1500", precio_costo="900").data["id"]

    def mover(self, accion, producto=None, **datos):
        return self.client.post(f"/api/productos/{producto or self.id}/{accion}/", datos)

    def test_producto_nuevo_empieza_sin_stock_en_rojo(self):
        p = self.client.get(f"/api/productos/{self.id}/").data
        self.assertEqual((Decimal(p["stock_actual"]), p["semaforo"]), (Decimal("0"), "ROJO"))

    def test_ingreso_suma_y_queda_registrado(self):  # RF-34, RF-35
        r = self.mover("ingreso", cantidad="12.5", motivo="Frigorífico Sur")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(Decimal(r.data["stock_actual"]), Decimal("12.5"))
        self.assertEqual(r.data["semaforo"], "VERDE")
        m = MovimientoStock.objects.get(producto_id=self.id)
        self.assertEqual((m.tipo, m.cantidad, m.stock_resultante), ("INGRESO", Decimal("12.5"), Decimal("12.5")))
        self.assertEqual(m.costo_unitario, Decimal("4800.50"))  # el costo del producto en ese momento
        self.assertEqual(m.valor, Decimal("60006.25"))
        self.assertEqual(m.usuario, self.usuarios[Rol.ENCARGADO])
        self.assertEqual(m.turno.usuario, self.usuarios[Rol.ENCARGADO])  # RF-24: queda en su turno
        self.assertEqual(m.motivo, "Frigorífico Sur")

    def test_ingreso_con_otro_costo_no_cambia_el_precio_del_producto(self):
        self.mover("ingreso", cantidad="2", costo_unitario="5000")
        self.assertEqual(MovimientoStock.objects.get(producto_id=self.id).costo_unitario, Decimal("5000"))
        self.assertEqual(Producto.objects.get(pk=self.id).precio_costo, Decimal("4800.50"))

    def test_movimiento_de_un_administrador_no_tiene_turno(self):
        self.entrar_como(Rol.ADMINISTRADOR)
        self.assertEqual(self.mover("ingreso", cantidad="1").status_code, 200)
        self.assertIsNone(MovimientoStock.objects.get(producto_id=self.id).turno)

    def test_semaforo_segun_el_minimo(self):  # RF-38
        self.client.patch(f"/api/productos/{self.id}/", {"stock_minimo": "5"})
        self.assertEqual(self.mover("ingreso", cantidad="5").data["semaforo"], "AMARILLO")
        self.assertEqual(self.mover("ingreso", cantidad="0.001").data["semaforo"], "VERDE")
        self.assertEqual(self.mover("perdida", cantidad="5.001", motivo="Vencido").data["semaforo"], "ROJO")

    def test_cambiar_el_minimo_queda_en_el_historial(self):
        r = self.client.patch(f"/api/productos/{self.id}/", {"stock_minimo": "2.5"})
        self.assertEqual(r.status_code, 200, r.data)
        cambio = CambioProducto.objects.get(producto_id=self.id, accion="EDICION")
        self.assertEqual(cambio.detalle, "Stock mínimo: 0 → 2,5")
        self.assertIn("stock_minimo", self.client.patch(f"/api/productos/{self.id}/", {"stock_minimo": "-1"}).data)

    def test_el_stock_no_se_escribe_a_mano(self):  # RN-09
        self.client.patch(f"/api/productos/{self.id}/", {"stock_actual": "99"})
        self.assertEqual(Producto.objects.get(pk=self.id).stock_actual, Decimal("0"))
        self.assertEqual(Decimal(self.alta(nombre="Muslo", stock_actual="50").data["stock_actual"]), Decimal("0"))

    def test_perdida_resta_y_pide_motivo(self):  # RF-36
        self.mover("ingreso", cantidad="10")
        self.assertIn("motivo", self.mover("perdida", cantidad="1").data)
        r = self.mover("perdida", cantidad="1.25", motivo="Mal estado")
        self.assertEqual(Decimal(r.data["stock_actual"]), Decimal("8.75"))
        m = MovimientoStock.objects.filter(producto_id=self.id, tipo="PERDIDA").get()
        self.assertEqual((m.cantidad, m.motivo), (Decimal("-1.25"), "Mal estado"))

    def test_no_se_puede_perder_mas_de_lo_que_hay(self):
        self.mover("ingreso", cantidad="3")
        r = self.mover("perdida", cantidad="4", motivo="Rotura")
        self.assertEqual(r.status_code, 400)
        self.assertIn("recuento", str(r.data["cantidad"]))
        self.assertEqual(Producto.objects.get(pk=self.id).stock_actual, Decimal("3"))

    def test_recuento_ajusta_a_lo_contado(self):  # RF-37
        self.mover("ingreso", cantidad="10")
        r = self.mover("ajuste", stock_real="8.4", motivo="Recuento de inventario")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(Decimal(r.data["stock_actual"]), Decimal("8.4"))
        m = MovimientoStock.objects.filter(producto_id=self.id, tipo="AJUSTE").get()
        self.assertEqual((m.cantidad, m.stock_resultante), (Decimal("-1.6"), Decimal("8.4")))
        # Si coincide, no hay nada que ajustar; y sin motivo no se acepta
        self.assertEqual(self.mover("ajuste", stock_real="8.4", motivo="Recuento").status_code, 400)
        self.assertIn("motivo", self.mover("ajuste", stock_real="9").data)
        self.assertIn("stock_real", self.mover("ajuste", stock_real="-1", motivo="x").data)

    def test_por_unidad_no_admite_decimales(self):  # RF-32
        self.assertIn("cantidad", self.mover("ingreso", producto=self.agua, cantidad="2.5").data)
        self.assertEqual(self.mover("ingreso", producto=self.agua, cantidad="24").status_code, 200)
        self.assertIn("stock_real", self.mover("ajuste", producto=self.agua, stock_real="1.5", motivo="x").data)

    def test_cantidades_invalidas(self):
        for cantidad in ("0", "-3", "abc", ""):
            self.assertEqual(self.mover("ingreso", cantidad=cantidad).status_code, 400, cantidad)
        self.assertEqual(MovimientoStock.objects.count(), 0)

    def test_no_se_carga_stock_a_un_producto_dado_de_baja(self):
        self.client.post(f"/api/productos/{self.id}/desactivar/")
        self.assertEqual(self.mover("ingreso", cantidad="1").status_code, 400)

    def test_empleado_ve_el_stock_pero_no_lo_mueve(self):  # matriz 4.3
        self.mover("ingreso", cantidad="4")
        self.entrar_como(Rol.EMPLEADO)
        p = self.client.get(f"/api/productos/{self.id}/").data
        self.assertEqual((Decimal(p["stock_actual"]), p["semaforo"]), (Decimal("4"), "VERDE"))
        for accion, datos in (("ingreso", {"cantidad": "1"}), ("perdida", {"cantidad": "1", "motivo": "x"}),
                              ("ajuste", {"stock_real": "1", "motivo": "x"})):
            self.assertEqual(self.mover(accion, **datos).status_code, 403, accion)
        self.assertEqual(self.client.get("/api/movimientos/").status_code, 403)

    def test_historial_de_movimientos_con_filtros(self):
        self.mover("ingreso", cantidad="10")
        self.mover("perdida", cantidad="1", motivo="Vencido")
        self.mover("ingreso", producto=self.agua, cantidad="6")
        r = self.client.get("/api/movimientos/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data), 3)
        self.assertEqual(r.data[0]["producto_nombre"], "Agua 2 L")  # lo más nuevo primero
        self.assertEqual(Decimal(r.data[0]["valor"]), Decimal("5400.00"))
        self.assertEqual(len(self.client.get(f"/api/movimientos/?producto={self.id}").data), 2)
        self.assertEqual(len(self.client.get("/api/movimientos/?tipo=PERDIDA").data), 1)
        self.assertEqual(len(self.client.get("/api/movimientos/?hasta=2020-01-01").data), 0)
        self.assertEqual(self.client.get("/api/movimientos/?desde=ayer").status_code, 400)


class PresentacionTests(BaseProductos):
    """Productos que llegan en caja, cajón, bandeja, etc. (RF-83 a RF-85)."""

    def setUp(self):
        super().setUp()
        verduras = Categoria.objects.get(seccion__nombre="Verdulería", nombre="Verduras")
        self.tomate = self.alta(nombre="Tomate", categoria=verduras.id, unidad="KG", precio_venta="2000",
                                precio_costo="1000", presentacion="CAJON", contenido="18").data
        self.gaseosa = self.alta(nombre="Gaseosa", categoria=self.bebidas.id, unidad="UNIDAD", precio_venta="2600",
                                 precio_costo="1800", presentacion="PACK", contenido="6").data

    def ingreso(self, producto, **datos):
        return self.client.post(f"/api/productos/{producto['id']}/ingreso/", datos)

    def test_alta_con_presentacion(self):
        self.assertEqual(self.tomate["presentacion_texto"], "Cajón de 18 kg")
        self.assertEqual(self.gaseosa["presentacion_texto"], "Pack de 6 u.")
        suelto = self.alta(nombre="Banana").data
        self.assertEqual((suelto["presentacion"], suelto["contenido"], suelto["presentacion_texto"]), ("SUELTO", None, "Suelto"))

    def test_presentacion_necesita_contenido(self):
        self.assertIn("contenido", self.alta(nombre="Papa", presentacion="BOLSA").data)
        self.assertIn("contenido", self.alta(nombre="Papa", presentacion="BOLSA", contenido="0").data)
        self.assertIn("presentacion", self.alta(nombre="Papa", presentacion="TACHO", contenido="5").data)
        # Por unidad, cada caja trae un número entero
        self.assertIn("contenido", self.alta(nombre="Agua", categoria=self.bebidas.id, unidad="UNIDAD",
                                             presentacion="CAJA", contenido="6.5").data)

    def test_llegan_cajones_y_el_sistema_calcula_los_kilos(self):
        r = self.ingreso(self.tomate, bultos="3")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(Decimal(r.data["stock_actual"]), Decimal("54"))
        m = MovimientoStock.objects.get(producto_id=self.tomate["id"])
        self.assertEqual((m.cantidad, m.motivo), (Decimal("54"), "3 cajones × 18 kg"))

    def test_cajon_con_otro_peso_y_costo_por_cajon(self):
        r = self.ingreso(self.tomate, bultos="1", contenido="20", costo_bulto="24000", motivo="Don Luis")
        self.assertEqual(Decimal(r.data["stock_actual"]), Decimal("20"))
        m = MovimientoStock.objects.get(producto_id=self.tomate["id"])
        self.assertEqual(m.costo_unitario, Decimal("1200.00"))  # 24000 / 20 kg
        self.assertEqual(m.motivo, "1 cajón × 20 kg · Don Luis")
        # El contenido habitual del producto no cambia
        self.assertEqual(Producto.objects.get(pk=self.tomate["id"]).contenido, Decimal("18"))

    def test_packs_por_unidad(self):
        self.assertEqual(Decimal(self.ingreso(self.gaseosa, bultos="4").data["stock_actual"]), Decimal("24"))
        self.assertIn("bultos", self.ingreso(self.gaseosa, bultos="0.25").data)  # 1,5 gaseosas no existe
        self.assertEqual(Decimal(self.ingreso(self.gaseosa, bultos="0.5").data["stock_actual"]), Decimal("27"))

    def test_tambien_se_puede_cargar_suelto(self):
        self.assertEqual(Decimal(self.ingreso(self.tomate, cantidad="7.5").data["stock_actual"]), Decimal("7.5"))

    def test_errores_al_cargar_por_bulto(self):
        suelto = self.alta(nombre="Banana").data
        self.assertIn("bultos", self.ingreso(suelto, bultos="2").data)
        self.assertIn("bultos", self.ingreso(self.tomate, bultos="0").data)
        self.assertIn("cantidad", self.ingreso(self.tomate).data)
        self.assertEqual(MovimientoStock.objects.count(), 0)

    def test_elegir_en_que_llego_aunque_el_producto_sea_suelto(self):  # RF-121
        banana = self.alta(nombre="Banana").data  # cargada como «suelto», por kilo
        r = self.ingreso(banana, presentacion="CAJON", bultos="2", contenido="20")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(Decimal(r.data["stock_actual"]), Decimal("40"))
        self.assertEqual(MovimientoStock.objects.get(producto_id=banana["id"]).motivo, "2 cajones × 20 kg")
        # El producto recuerda en qué llega: el stock ya se puede ver en cajones
        self.assertEqual(r.data["presentacion_texto"], "Cajón de 20 kg")
        detalle = CambioProducto.objects.get(producto_id=banana["id"], accion="EDICION").detalle
        self.assertEqual(detalle, "Llega en: Suelto → Cajón de 20 kg")
        self.assertIn("contenido", self.ingreso(self.alta(nombre="Pera").data, presentacion="BOLSA", bultos="2").data)

    def test_otra_presentacion_por_esta_vez(self):
        # El tomate llega en cajón de 18 kg, pero esta vez vino en bolsas de 10: el producto no cambia
        r = self.ingreso(self.tomate, presentacion="BOLSA", bultos="3", contenido="10")
        self.assertEqual(Decimal(r.data["stock_actual"]), Decimal("30"))
        self.assertEqual(MovimientoStock.objects.get(producto_id=self.tomate["id"]).motivo, "3 bolsas × 10 kg")
        self.assertEqual(r.data["presentacion_texto"], "Cajón de 18 kg")
        self.assertIn("presentacion", self.ingreso(self.tomate, presentacion="TACHO", bultos="1").data)

    def test_perdida_y_recuento_por_cajon(self):  # RF-121
        self.ingreso(self.tomate, bultos="5")  # 90 kg
        r = self.client.post(f"/api/productos/{self.tomate['id']}/perdida/", {"bultos": "1", "motivo": "Se pudrió"})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(Decimal(r.data["stock_actual"]), Decimal("72"))
        perdida = MovimientoStock.objects.get(producto_id=self.tomate["id"], tipo="PERDIDA")
        self.assertEqual((perdida.cantidad, perdida.motivo), (Decimal("-18"), "Se pudrió · 1 cajón × 18 kg"))
        r = self.client.post(f"/api/productos/{self.tomate['id']}/perdida/", {"bultos": "9", "motivo": "x"})
        self.assertEqual(r.status_code, 400)  # no se puede perder más de lo que hay
        # Recuento: se contaron 3 cajones y medio
        r = self.client.post(f"/api/productos/{self.tomate['id']}/ajuste/", {"bultos": "3.5", "motivo": "Recuento"})
        self.assertEqual(Decimal(r.data["stock_actual"]), Decimal("63"))
        ajuste = MovimientoStock.objects.get(producto_id=self.tomate["id"], tipo="AJUSTE")
        self.assertEqual(ajuste.motivo, "Recuento · se contaron 3,5 cajones × 18 kg")
        r = self.client.post(f"/api/productos/{self.tomate['id']}/ajuste/", {"bultos": "0", "motivo": "No quedó nada"})
        self.assertEqual(Decimal(r.data["stock_actual"]), Decimal("0"))
        # Sin cantidad ni cajones, falta el dato
        self.assertIn("cantidad", self.client.post(f"/api/productos/{self.tomate['id']}/perdida/", {"motivo": "x"}).data)
        self.assertIn("stock_real", self.client.post(f"/api/productos/{self.tomate['id']}/ajuste/", {"motivo": "x"}).data)

    def test_cambiar_la_presentacion_queda_en_el_historial(self):
        r = self.client.patch(f"/api/productos/{self.tomate['id']}/", {"presentacion": "CAJA", "contenido": "10"})
        self.assertEqual(r.status_code, 200, r.data)
        detalle = CambioProducto.objects.get(producto_id=self.tomate["id"], accion="EDICION").detalle
        self.assertEqual(detalle, "Llega en: Cajón de 18 kg → Caja de 10 kg")
        r = self.client.patch(f"/api/productos/{self.tomate['id']}/", {"presentacion": "SUELTO"})
        self.assertIsNone(r.data["contenido"])

    def test_empleado_no_carga_lo_que_llega(self):
        self.entrar_como(Rol.EMPLEADO)
        self.assertEqual(self.ingreso(self.tomate, bultos="1").status_code, 403)
        self.assertEqual(self.alta(nombre="Otro", presentacion="CAJA", contenido="5").status_code, 403)


class PreciosTests(BaseProductos):
    """Módulo de precios (RF-90 a RF-94)."""

    def setUp(self):
        super().setUp()
        self.pechuga = self.alta().data["id"]  # venta 6500 / costo 4800,50
        self.alitas = self.alta(nombre="alitas", precio_venta="3333.00", precio_costo="2000.00").data["id"]
        self.gaseosa = self.alta(nombre="gaseosa", categoria=self.bebidas.id, unidad="UNIDAD",
                                 precio_venta="1500.00", precio_costo="1000.00").data["id"]

    def ajuste(self, **datos):
        datos = {"categoria": self.pollo.id, "porcentaje": "20", **datos}
        return self.client.post("/api/precios/ajuste/", datos, format="json")

    def precios(self, pk):
        p = Producto.objects.get(pk=pk)
        return str(p.precio_venta), str(p.precio_costo)

    def test_vista_previa_no_guarda(self):
        r = self.ajuste()
        self.assertEqual(r.status_code, 200, r.data)
        self.assertFalse(r.data["aplicado"])
        self.assertEqual([f["nombre"] for f in r.data["productos"]], ["Alitas", "Pechuga"])
        self.assertEqual(str(r.data["productos"][1]["precio_venta_nuevo"]), "7800.00")
        self.assertEqual(self.precios(self.pechuga), ("6500.00", "4800.50"))
        self.assertFalse(CambioProducto.objects.filter(accion="PRECIO").exists())

    def test_aumento_a_toda_la_categoria(self):
        r = self.ajuste(confirmar=True)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["cambiados"], 2)
        self.assertEqual(self.precios(self.pechuga), ("7800.00", "4800.50"))  # el costo no se toca
        self.assertEqual(self.precios(self.alitas), ("3999.60", "2000.00"))
        self.assertEqual(self.precios(self.gaseosa), ("1500.00", "1000.00"))  # otra categoría: igual
        cambio = CambioProducto.objects.get(producto_id=self.pechuga, accion="PRECIO")
        self.assertEqual(cambio.detalle, "Venta $6500.00 → $7800.00 · +20 % a toda la categoría Pollo")
        self.assertEqual(cambio.realizado_por, self.usuarios[Rol.ENCARGADO])

    def test_rebaja_con_redondeo(self):
        self.ajuste(porcentaje="-10", redondeo=100, confirmar=True)
        self.assertEqual(self.precios(self.pechuga)[0], "5900.00")  # 5850 → 5900
        self.assertEqual(self.precios(self.alitas)[0], "3000.00")   # 2999,70 → 3000

    def test_costo_y_venta_juntos(self):
        self.ajuste(aplicar_a="AMBOS", confirmar=True)
        self.assertEqual(self.precios(self.pechuga), ("7800.00", "5760.60"))
        detalle = CambioProducto.objects.get(producto_id=self.pechuga, accion="PRECIO").detalle
        self.assertIn("Costo $4800.50 → $5760.60", detalle)

    def test_solo_costo(self):
        self.ajuste(aplicar_a="COSTO", confirmar=True)
        self.assertEqual(self.precios(self.pechuga), ("6500.00", "5760.60"))

    def test_solo_algunos_productos(self):
        r = self.ajuste(productos=[self.alitas, self.gaseosa], confirmar=True)
        self.assertEqual(r.data["cambiados"], 1)  # la gaseosa no es de Pollo: se ignora
        self.assertEqual(self.precios(self.alitas)[0], "3999.60")
        self.assertEqual(self.precios(self.pechuga)[0], "6500.00")
        self.assertEqual(self.precios(self.gaseosa)[0], "1500.00")
        self.assertIn("productos de la categoría Pollo", CambioProducto.objects.get(accion="PRECIO").detalle)

    def test_los_dados_de_baja_no_cambian(self):
        self.client.post(f"/api/productos/{self.alitas}/desactivar/")
        r = self.ajuste(confirmar=True)
        self.assertEqual(r.data["cambiados"], 1)
        self.assertEqual(self.precios(self.alitas)[0], "3333.00")

    def test_validaciones(self):
        self.assertIn("porcentaje", self.ajuste(porcentaje="0").data)
        self.assertIn("porcentaje", self.ajuste(porcentaje="-95").data)
        self.assertIn("porcentaje", self.ajuste(porcentaje="900").data)
        self.assertIn("redondeo", self.ajuste(redondeo=7).data)
        self.assertEqual(self.ajuste(categoria=99999).status_code, 400)
        self.assertEqual(self.ajuste(productos=[]).status_code, 400)
        vacia = Categoria.objects.create(seccion=self.pollo.seccion, nombre="Vacía de prueba")
        self.assertEqual(self.ajuste(categoria=vacia.id).status_code, 400)

    def test_empleado_no_cambia_precios(self):
        self.entrar_como(Rol.EMPLEADO)
        self.assertEqual(self.ajuste(confirmar=True).status_code, 403)
        r = self.client.post(f"/api/productos/{self.pechuga}/precio/", {"precio_venta": "1.00"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.precios(self.pechuga)[0], "6500.00")

    def test_precio_individual(self):
        r = self.client.post(f"/api/productos/{self.pechuga}/precio/", {"precio_venta": "7000"})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self.precios(self.pechuga), ("7000.00", "4800.50"))
        detalle = CambioProducto.objects.get(producto_id=self.pechuga, accion="PRECIO").detalle
        self.assertEqual(detalle, "Venta $6500.00 → $7000.00 · cambio individual")

    def test_precio_individual_validaciones(self):
        url = f"/api/productos/{self.pechuga}/precio/"
        self.assertEqual(self.client.post(url, {}).status_code, 400)
        self.assertEqual(self.client.post(url, {"precio_venta": "0"}).status_code, 400)
        self.assertEqual(self.client.post(url, {"precio_costo": "-1"}).status_code, 400)
        self.assertEqual(self.client.post(url, {"precio_venta": "6500.00"}).status_code, 400)  # igual al actual
        self.assertFalse(CambioProducto.objects.filter(accion="PRECIO").exists())

    def test_editar_producto_sigue_sin_cambiar_precios(self):
        self.client.patch(f"/api/productos/{self.pechuga}/", {"precio_venta": "1.00"})
        self.assertEqual(self.precios(self.pechuga)[0], "6500.00")
