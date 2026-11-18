"""Reglas de turnos, cierre del día, resumen por período y registro de actividad.

Las vistas (api.py), el login y el planificador de las 00:45 usan estas funciones.
"""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from clientes.models import CambioCliente, MovimientoCuenta
from compras.models import Compra, PagoCompra
from core.dia import fecha_local, inicio_del_dia  # el día del mercado va de 00:45 a 00:45
from gastos.models import Gasto
from notificaciones import servicios as avisos
from productos.models import CambioProducto, MovimientoStock, Seccion
from usuarios.models import CambioUsuario, RegistroAcceso
from ventas.models import DetalleVenta, Venta

from .models import CierreDiario, Turno

CENTAVOS = Decimal("0.01")
MAX_DIAS_ATRASADOS = 366  # si la computadora estuvo apagada, se ponen al día hasta un año de cierres
MAX_CIERRES_AVISADOS = 3  # al ponerse al día después de varios días apagada, solo se avisan los últimos
# Una cuenta abierta desde un día anterior y sin uso en este rato es una cuenta olvidada (RF-27)
TIEMPO_DE_OLVIDO = timedelta(hours=1)


# ---------- Fechas ----------

def rango_de_fechas(desde, hasta):
    """Momento inicial y final (sin incluir) de un período de días completos."""
    return inicio_del_dia(desde), inicio_del_dia(hasta + timedelta(days=1))


# ---------- Turnos ----------

def lleva_turno(usuario):
    """Empleados y encargados llevan turno; los dueños no."""
    return not usuario.es_administrador


def turno_abierto(usuario):
    return Turno.objects.filter(usuario=usuario, fin__isnull=True).first()


def abrir_turno(usuario):
    """RF-21: al iniciar sesión se abre el turno. Si ya tenía uno abierto, sigue con ese (RN-07).

    Si el que tenía abierto es una cuenta olvidada de un día anterior, se cierra y empieza uno nuevo.
    """
    if not lleva_turno(usuario):
        return None
    cerrar_turno_olvidado(usuario)
    turno, _ = Turno.objects.get_or_create(usuario=usuario, fin__isnull=True)
    return turno


def cerrar_turno(usuario, tipo, cuando=None):
    """RF-23: al cerrar sesión termina el turno y queda guardada la hora."""
    cuando = cuando or timezone.now()
    return Turno.objects.filter(usuario=usuario, fin__isnull=True).update(
        fin=cuando, tipo_cierre=tipo, ultima_actividad=cuando
    )


def cerrar_turno_olvidado(usuario, ahora=None):
    """RF-27: la cuenta que alguien se olvidó de cerrar. Devuelve True si había una y se cerró.

    El sistema ya no les cierra la cuenta a los empleados a ninguna hora: la cierra cada uno al irse.
    Pero si alguien se la olvidó abierta (es de un día anterior y hace más de una hora que no la usa),
    cuando esa persona vuelve se le cierra en el último momento en que usó el sistema y queda
    marcada para que el dueño revise la hora real de salida.
    """
    ahora = ahora or timezone.now()
    turno = turno_abierto(usuario)
    if turno is None or turno.inicio >= inicio_del_dia(fecha_local(ahora)):
        return False
    if ahora - turno.ultima_actividad < TIEMPO_DE_OLVIDO:
        return False  # sigue trabajando pasada la hora del cierre: no se toca
    fin = max(turno.ultima_actividad, turno.inicio)
    return bool(Turno.objects.filter(pk=turno.pk, fin__isnull=True).update(
        fin=fin, tipo_cierre=Turno.SISTEMA, para_revisar=True
    ))


# ---------- Cierre automático de las 00:45 ----------

def cerrar_dias_pendientes(ahora=None):
    """Hace la caja de los días que ya terminaron. Se puede llamar todas las veces que haga falta.

    Genera el cierre de cada día terminado que todavía no lo tenga y les avisa a los dueños
    (aviso en el sistema, Telegram y correo). NO cierra las cuentas de los empleados: cada uno
    cierra la suya al irse.

    Lo ejecuta el planificador apenas pasan las 00:45. Si la computadora estaba apagada a esa
    hora, se pone al día sola cuando se enciende o en el próximo inicio de sesión.
    """
    ahora = ahora or timezone.now()
    hoy = fecha_local(ahora)
    limpiar_buzon(hoy)

    ultimo = CierreDiario.objects.order_by("-fecha").values_list("fecha", flat=True).first()
    if ultimo:
        fecha = ultimo + timedelta(days=1)
    else:
        comienzos = [
            Turno.objects.order_by("inicio").values_list("inicio", flat=True).first(),
            MovimientoStock.objects.order_by("fecha_hora").values_list("fecha_hora", flat=True).first(),
        ]
        comienzos = [c for c in comienzos if c]
        if not comienzos:
            return []  # el sistema todavía no se usó
        fecha = fecha_local(min(comienzos))
    fecha = max(fecha, hoy - timedelta(days=MAX_DIAS_ATRASADOS))

    generados = []
    while fecha < hoy:
        cierre, nuevo, r = generar_cierre(fecha)
        if nuevo:
            generados.append((cierre, r))
        fecha += timedelta(days=1)
    for cierre, r in generados[-MAX_CIERRES_AVISADOS:]:
        avisos.avisar_cierre(cierre, r)
    return [cierre for cierre, _ in generados]


def limpiar_buzon(hoy):
    """Limpieza semanal del buzón de recibos: cada domingo salen los recibos de más de una semana.

    El corte es el domingo anterior al último domingo, así que en el buzón siempre quedan a mano
    los recibos de esta semana y los de la semana pasada. Las ventas NO se borran: solo dejan
    de aparecer en el buzón. Se puede llamar todas las veces que haga falta.
    """
    ultimo_domingo = hoy - timedelta(days=(hoy.weekday() + 1) % 7)  # hoy mismo si es domingo
    corte = inicio_del_dia(ultimo_domingo - timedelta(days=7))
    return Venta.objects.filter(en_buzon=True, fecha_hora__lt=corte).update(en_buzon=False)


def generar_cierre(fecha):
    """Guarda la foto de los totales de un día. Devuelve (cierre, si es nuevo, el resumen del día)."""
    r = resumen(fecha, fecha)
    cierre, nuevo = CierreDiario.objects.get_or_create(
        fecha=fecha,
        defaults={
            "turnos": r["personal"]["turnos"],
            "minutos_trabajados": r["personal"]["minutos"],
            "turnos_cerrados_por_sistema": r["personal"]["cerrados_por_sistema"],
            "movimientos_stock": r["mercaderia"]["movimientos"],
            "valor_ingresado": r["mercaderia"]["ingresos"]["valor"],
            "valor_perdidas": r["mercaderia"]["perdidas"]["valor"],
            "valor_ajustes": r["mercaderia"]["ajustes"]["valor"],
            "cambios": r["cambios"],
            "ventas_cantidad": r["ventas"]["cantidad"],
            "ventas_total": r["ventas"]["total"],
            "ventas_efectivo": r["ventas"]["efectivo"],
            "ganancia_bruta": r["ventas"]["ganancia_bruta"],
            "ventas_fiado": r["ventas"]["fiado"],
            "cobros_cuenta": r["cuenta_corriente"]["total"],
            "cobros_cuenta_efectivo": r["cuenta_corriente"]["efectivo"],
            "gastos_cantidad": r["gastos"]["cantidad"],
            "gastos_total": r["gastos"]["total"],
            "compras_total": r["comerciantes"]["comprado"],
            "pagos_comerciantes": r["comerciantes"]["pagado"],
            "pagos_comerciantes_efectivo": r["comerciantes"]["pagado_efectivo"],
        },
    )
    return cierre, nuevo, r


# ---------- Ventas de un período ----------

def resumen_de_ventas(inicio, fin, por_dia=None):
    """Dinero vendido entre dos momentos: total, por medio de pago, por sección y ganancia bruta.

    Las ventas anuladas no suman. La ganancia bruta es lo vendido menos lo que costó esa mercadería
    (todavía sin restar gastos, que llegan con el módulo de gastos).
    Si se pasa el diccionario `por_dia`, se le suma lo vendido en cada fecha.
    """
    medios = {clave: {"medio": clave, "nombre": nombre, "cantidad": 0, "total": Decimal(0)}
              for clave, nombre in Venta.MEDIOS}
    total = Decimal(0)
    cantidad = anuladas = 0
    modificadas = 0
    reemplazadas = set(
        Venta.objects.filter(fecha_hora__gte=inicio, fecha_hora__lt=fin, correcciones__isnull=False).values_list("pk", flat=True)
    )
    for v in Venta.objects.filter(fecha_hora__gte=inicio, fecha_hora__lt=fin):
        if v.pk in reemplazadas:
            modificadas += 1  # su versión corregida es la que suma
            continue
        if v.anulada:
            anuladas += 1
            continue
        cantidad += 1
        total += v.total
        medios[v.medio_pago]["cantidad"] += 1
        medios[v.medio_pago]["total"] += v.total
        if por_dia is not None:
            por_dia[fecha_local(v.fecha_hora)]["vendido"] += v.total

    costo = Decimal(0)
    secciones = defaultdict(lambda: {"total": Decimal(0), "costo": Decimal(0)})
    detalles = DetalleVenta.objects.filter(
        venta__fecha_hora__gte=inicio, venta__fecha_hora__lt=fin, venta__anulada=False
    ).select_related("producto__categoria__seccion")
    for d in detalles:
        costo_renglon = (d.cantidad * d.costo_unitario).quantize(CENTAVOS)
        costo += costo_renglon
        s = secciones[d.producto.categoria.seccion.nombre]
        s["total"] += d.subtotal
        s["costo"] += costo_renglon

    return {
        "cantidad": cantidad,
        "anuladas": anuladas,
        "modificadas": modificadas,
        "total": _dinero(total),
        "efectivo": _dinero(medios[Venta.EFECTIVO]["total"]),
        "fiado": _dinero(medios[Venta.CUENTA]["total"]),  # vendido en cuenta corriente: no entró plata
        "costo": _dinero(costo),
        "ganancia_bruta": _dinero(total - costo),
        "por_medio": [{**m, "total": _dinero(m["total"])} for m in medios.values() if m["cantidad"]],
        "por_seccion": [
            {"seccion": nombre, "total": _dinero(s["total"]), "ganancia_bruta": _dinero(s["total"] - s["costo"])}
            for nombre, s in sorted(secciones.items())
        ],
    }


def resumen_de_cuentas(inicio, fin):
    """Plata que entró entre dos momentos porque los clientes pagaron su cuenta corriente, por medio de pago."""
    nombres = dict(Venta.MEDIOS)
    medios = {}
    total = Decimal(0)
    cobros = 0
    pagos = MovimientoCuenta.objects.filter(tipo=MovimientoCuenta.PAGO, fecha_hora__gte=inicio, fecha_hora__lt=fin)
    for m in pagos:
        cobros += 1
        total -= m.importe  # el pago se guarda en negativo: baja la deuda
        fila = medios.setdefault(m.medio_pago, {"medio": m.medio_pago, "nombre": nombres.get(m.medio_pago, m.medio_pago),
                                               "cantidad": 0, "total": Decimal(0)})
        fila["cantidad"] += 1
        fila["total"] -= m.importe
    ajustes = MovimientoCuenta.objects.filter(tipo=MovimientoCuenta.AJUSTE, fecha_hora__gte=inicio, fecha_hora__lt=fin).count()
    return {
        "cobros": cobros,
        "ajustes": ajustes,
        "total": _dinero(total),
        "efectivo": _dinero(medios.get(Venta.EFECTIVO, {}).get("total", 0)),
        "por_medio": [{**m, "total": _dinero(m["total"])} for m in medios.values()],
    }


def resumen_de_compras(inicio, fin):
    """Compras a comerciantes anotadas entre dos momentos y plata que se les pagó en ese rato.

    Lo pagado cuenta el día en que se pagó, aunque la compra sea de antes. Las compras anuladas no suman.
    """
    compras = comprado = 0
    for c in Compra.objects.filter(fecha_hora__gte=inicio, fecha_hora__lt=fin, anulada=False):
        compras += 1
        comprado += c.costo_total
    pagos = 0
    pagado = efectivo = Decimal(0)
    for p in PagoCompra.objects.filter(fecha_hora__gte=inicio, fecha_hora__lt=fin, compra__anulada=False):
        pagos += 1
        pagado += p.importe
        if p.medio_pago == Venta.EFECTIVO:
            efectivo += p.importe
    deuda = sum((c.falta for c in Compra.objects.filter(anulada=False)), Decimal(0))
    return {"compras": compras, "comprado": _dinero(comprado), "pagos": pagos, "pagado": _dinero(pagado),
            "pagado_efectivo": _dinero(efectivo), "deuda_actual": _dinero(deuda)}


def resumen_de_gastos(inicio, fin, por_dia=None):
    """Gastos anotados entre dos momentos. Los anulados no suman. Los montos van en positivo."""
    total = Decimal(0)
    cantidad = anulados = 0
    lista = []
    for g in Gasto.objects.filter(fecha_hora__gte=inicio, fecha_hora__lt=fin).select_related("usuario"):
        if g.anulado:
            anulados += 1
            continue
        cantidad += 1
        total += g.monto
        if por_dia is not None:
            por_dia[fecha_local(g.fecha_hora)]["gastos"] += g.monto
        if len(lista) < 300:
            lista.append({"id": g.id, "fecha_hora": g.fecha_hora, "monto": _dinero(g.monto),
                          "proposito": g.proposito, "usuario": g.usuario.nombre_completo})
    return {"cantidad": cantidad, "anulados": anulados, "total": _dinero(total), "lista": lista}


def cuenta_final(ventas, cuentas, gastos, compras):
    """La cuenta del período (RF-109): la plata que entró menos los gastos.

    Lo vendido fiado no cuenta como plata que entró; los pagos de cuentas corrientes, sí.
    Los gastos salen de la caja, así que también se restan del efectivo que debería haber.
    """
    entro = Decimal(ventas["total"]) - Decimal(ventas["fiado"]) + Decimal(cuentas["total"])
    total_gastos = Decimal(gastos["total"])
    # Lo que se les pagó a los comerciantes también es plata que salió (RF-118)
    pagos = Decimal(compras["pagado"])
    efectivo = (Decimal(ventas["efectivo"]) + Decimal(cuentas["efectivo"]) - total_gastos
                - Decimal(compras["pagado_efectivo"]))
    return {"entro": _dinero(entro), "gastos": _dinero(total_gastos), "pagos_comerciantes": _dinero(pagos),
            "resultado": _dinero(entro - total_gastos - pagos), "efectivo": _dinero(efectivo)}


# ---------- Resumen por período (día, semana o mes) ----------

def _dinero(valor):
    return str(Decimal(valor).quantize(CENTAVOS))


def _cantidad(valor):
    return str(Decimal(valor).quantize(Decimal("0.001")))


def resumen(desde, hasta):
    """Todo lo que entró y salió entre dos fechas (incluidas), más las horas trabajadas."""
    inicio, fin = rango_de_fechas(desde, hasta)

    dias = {}
    fecha = desde
    while fecha <= hasta:
        dias[fecha] = {"fecha": fecha.isoformat(), "vendido": Decimal(0), "valor_ingresado": Decimal(0),
                       "valor_perdidas": Decimal(0), "movimientos": 0, "minutos": 0, "gastos": Decimal(0)}
        fecha += timedelta(days=1)

    # --- Mercadería ---
    totales = {t: {"movimientos": 0, "valor": Decimal(0)}
               for t in (MovimientoStock.INGRESO, MovimientoStock.PERDIDA, MovimientoStock.AJUSTE, MovimientoStock.VENTA)}
    secciones = defaultdict(lambda: {"valor_ingresado": Decimal(0), "valor_perdidas": Decimal(0)})
    productos = {}

    movimientos = MovimientoStock.objects.filter(fecha_hora__gte=inicio, fecha_hora__lt=fin).select_related(
        "producto__categoria__seccion"
    )
    for m in movimientos:
        p = m.producto
        # Ingresos y pérdidas se muestran en positivo; el ajuste conserva el signo (sobró o faltó).
        # En las ventas, lo vendido suma y lo devuelto por una anulación resta.
        if m.tipo == MovimientoStock.AJUSTE:
            valor = m.valor
        elif m.tipo == MovimientoStock.VENTA:
            valor = -m.valor
        elif m.tipo == MovimientoStock.PERDIDA:
            valor = abs(m.valor)
        else:
            valor = m.valor  # ingreso: positivo; negativo si es la anulación de una compra
        totales[m.tipo]["movimientos"] += 1
        totales[m.tipo]["valor"] += valor

        fila = productos.setdefault(p.id, {
            "id": p.id, "nombre": p.nombre, "unidad": p.unidad, "seccion": p.categoria.seccion.nombre,
            "ingresado": Decimal(0), "perdido": Decimal(0), "ajustado": Decimal(0), "vendido": Decimal(0),
            "valor_ingresado": Decimal(0), "valor_perdidas": Decimal(0),
        })
        dia = dias[fecha_local(m.fecha_hora)]
        dia["movimientos"] += 1
        seccion = secciones[p.categoria.seccion.nombre]
        if m.tipo == MovimientoStock.INGRESO:
            fila["ingresado"] += m.cantidad
            fila["valor_ingresado"] += valor
            seccion["valor_ingresado"] += valor
            dia["valor_ingresado"] += valor
        elif m.tipo == MovimientoStock.PERDIDA:
            fila["perdido"] += abs(m.cantidad)
            fila["valor_perdidas"] += valor
            seccion["valor_perdidas"] += valor
            dia["valor_perdidas"] += valor
        elif m.tipo == MovimientoStock.AJUSTE:
            fila["ajustado"] += m.cantidad
        else:
            fila["vendido"] -= m.cantidad  # la venta es negativa; su anulación, positiva

    # --- Personal: horas trabajadas ---
    personas = {}
    cantidad_turnos = minutos_totales = por_sistema = para_revisar = 0
    abiertos = []  # quienes todavía no cerraron su cuenta
    for t in Turno.objects.filter(inicio__gte=inicio, inicio__lt=fin).select_related("usuario__rol"):
        minutos = t.minutos
        if t.abierto:
            abiertos.append({"id": t.usuario_id, "nombre": t.usuario.nombre_completo,
                             "inicio": t.inicio, "ultima_actividad": t.ultima_actividad})
        cantidad_turnos += 1
        minutos_totales += minutos
        por_sistema += t.tipo_cierre == Turno.SISTEMA
        para_revisar += t.para_revisar
        dias[fecha_local(t.inicio)]["minutos"] += minutos
        persona = personas.setdefault(t.usuario_id, {
            "id": t.usuario_id, "nombre": t.usuario.nombre_completo, "rol": t.usuario.rol.nombre,
            "turnos": 0, "minutos": 0, "para_revisar": 0,
        })
        persona["turnos"] += 1
        persona["minutos"] += minutos
        persona["para_revisar"] += t.para_revisar

    ventas = resumen_de_ventas(inicio, fin, por_dia=dias)
    cuentas = resumen_de_cuentas(inicio, fin)
    gastos = resumen_de_gastos(inicio, fin, por_dia=dias)
    compras = resumen_de_compras(inicio, fin)

    # Cambios registrados: usuarios, productos, movimientos de stock que no son de una venta, y ventas
    cambios = (
        totales_de_cambios(CambioUsuario, inicio, fin)
        + totales_de_cambios(CambioProducto, inicio, fin)
        + sum(t["movimientos"] for tipo, t in totales.items() if tipo != MovimientoStock.VENTA)
        + ventas["cantidad"] + ventas["anuladas"] + ventas["modificadas"]
        + totales_de_cambios(CambioCliente, inicio, fin) + cuentas["cobros"] + cuentas["ajustes"]
        + gastos["cantidad"] + gastos["anulados"] + compras["compras"] + compras["pagos"]
    )

    return {
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "ventas": ventas,
        "cuenta_corriente": cuentas,
        "gastos": gastos,
        "comerciantes": compras,
        "caja": cuenta_final(ventas, cuentas, gastos, compras),
        "mercaderia": {
            "movimientos": sum(t["movimientos"] for t in totales.values()),
            "ingresos": _total(totales[MovimientoStock.INGRESO]),
            "perdidas": _total(totales[MovimientoStock.PERDIDA]),
            "ajustes": _total(totales[MovimientoStock.AJUSTE]),
            "ventas": _total(totales[MovimientoStock.VENTA]),
            "por_seccion": [
                {"seccion": nombre, "valor_ingresado": _dinero(s["valor_ingresado"]),
                 "valor_perdidas": _dinero(s["valor_perdidas"])}
                for nombre, s in sorted(secciones.items())
            ],
            "por_producto": [
                {**f, **{k: _cantidad(f[k]) for k in ("ingresado", "perdido", "ajustado", "vendido")},
                 "valor_ingresado": _dinero(f["valor_ingresado"]), "valor_perdidas": _dinero(f["valor_perdidas"])}
                for f in sorted(productos.values(), key=lambda f: (f["seccion"], f["nombre"]))
            ],
        },
        "personal": {
            "turnos": cantidad_turnos,
            "minutos": minutos_totales,
            "cerrados_por_sistema": por_sistema,
            "para_revisar": para_revisar,
            "abiertos": abiertos,
            "por_persona": sorted(personas.values(), key=lambda p: p["nombre"]),
        },
        "cambios": cambios,
        "por_dia": [
            {**d, "vendido": _dinero(d["vendido"]), "gastos": _dinero(d["gastos"]),
             "valor_ingresado": _dinero(d["valor_ingresado"]),
             "valor_perdidas": _dinero(d["valor_perdidas"])}
            for d in dias.values()
        ],
    }


def _total(t):
    return {"movimientos": t["movimientos"], "valor": _dinero(t["valor"])}


def totales_de_cambios(modelo, inicio, fin):
    return modelo.objects.filter(fecha_hora__gte=inicio, fecha_hora__lt=fin).count()


# ---------- Actividad: todo lo que pasó en el sistema entre dos momentos ----------

MAX_EVENTOS = 500

ACCESO = "ACCESO"
USUARIOS = "USUARIOS"
PRODUCTOS = "PRODUCTOS"
STOCK = "STOCK"
TURNOS = "TURNOS"
VENTAS = "VENTAS"
CLIENTES = "CLIENTES"
GASTOS = "GASTOS"
COMPRAS = "COMPRAS"
GRUPOS = [ACCESO, USUARIOS, PRODUCTOS, STOCK, TURNOS, VENTAS, CLIENTES, GASTOS, COMPRAS]

SISTEMA = {"id": None, "nombre": "El sistema"}


def _persona(usuario):
    return {"id": usuario.id, "nombre": usuario.nombre_completo}


def _texto_cantidad(cantidad, producto):
    numero = f"{abs(cantidad).normalize():f}".replace(".", ",")
    return f"{numero} {'kg' if producto.unidad == 'KG' else 'u.'}"


def actividad(desde, hasta, usuario_id=None, grupo=None):
    """Lista de todo lo que pasó entre `desde` y `hasta`, lo más nuevo primero, y quién estaba de turno."""
    eventos = []

    def agregar(grupo_evento, momento, quien, titulo, detalle=None):
        eventos.append({"grupo": grupo_evento, "fecha_hora": momento, "quien": quien, "titulo": titulo,
                        "detalle": detalle or None})

    def en_rango(qs, campo="fecha_hora"):
        return qs.filter(**{f"{campo}__gte": desde, f"{campo}__lt": hasta})

    def quiere(grupo_evento):
        return grupo in (None, grupo_evento)

    if quiere(ACCESO):
        qs = en_rango(RegistroAcceso.objects.select_related("usuario"))
        if usuario_id:
            qs = qs.filter(usuario_id=usuario_id)
        for a in qs[:MAX_EVENTOS]:
            quien = _persona(a.usuario) if a.usuario else {"id": None, "nombre": f"«{a.nombre_usuario_ingresado}» (no existe)"}
            titulo = a.get_tipo_display()
            if a.tipo == RegistroAcceso.LOGIN and not a.exitoso:
                titulo = "Intento de ingreso fallido"
            agregar(ACCESO, a.fecha_hora, quien, titulo, a.dispositivo)

    if quiere(USUARIOS):
        qs = en_rango(CambioUsuario.objects.select_related("usuario", "realizado_por"))
        if usuario_id:
            qs = qs.filter(realizado_por_id=usuario_id)
        for c in qs[:MAX_EVENTOS]:
            detalle = c.usuario.nombre_completo + (f" · {c.detalle}" if c.detalle else "")
            agregar(USUARIOS, c.fecha_hora, _persona(c.realizado_por), c.get_accion_display(), detalle)

    if quiere(PRODUCTOS):
        qs = en_rango(CambioProducto.objects.select_related("producto", "realizado_por"))
        if usuario_id:
            qs = qs.filter(realizado_por_id=usuario_id)
        for c in qs[:MAX_EVENTOS]:
            detalle = c.producto.nombre + (f" · {c.detalle}" if c.detalle else "")
            agregar(PRODUCTOS, c.fecha_hora, _persona(c.realizado_por), c.get_accion_display(), detalle)

    if quiere(VENTAS):
        qs = en_rango(Venta.objects.select_related("usuario"))
        if usuario_id:
            qs = qs.filter(usuario_id=usuario_id)
        for v in qs.select_related("corrige_a")[:MAX_EVENTOS]:
            if v.corrige_a:
                # Una compra modificada después de pagar: se ve qué recibo reemplaza y cómo cambió el total
                agregar(VENTAS, v.fecha_hora, _persona(v.usuario), "Compra modificada",
                        f"Recibo N° {v.numero} reemplaza al N° {v.corrige_a.numero} · "
                        f"${v.corrige_a.total} → ${v.total} · {v.get_medio_pago_display()}")
            else:
                agregar(VENTAS, v.fecha_hora, _persona(v.usuario), "Venta",
                        f"Recibo N° {v.numero} · ${v.total} · {v.get_medio_pago_display()}")
        # Anulaciones de verdad (las reemplazadas por una modificación ya se ven arriba)
        qs = en_rango(Venta.objects.filter(anulada=True, correcciones__isnull=True).select_related("usuario", "anulada_por"), "anulada_en")
        if usuario_id:
            qs = qs.filter(anulada_por_id=usuario_id)
        for v in qs[:MAX_EVENTOS]:
            agregar(VENTAS, v.anulada_en, _persona(v.anulada_por), "Anulación de venta",
                    f"Recibo N° {v.numero} · ${v.total} · vendió {v.usuario.nombre_completo} · {v.motivo_anulacion}")

    if quiere(CLIENTES):
        qs = en_rango(CambioCliente.objects.select_related("cliente", "realizado_por"))
        if usuario_id:
            qs = qs.filter(realizado_por_id=usuario_id)
        for c in qs[:MAX_EVENTOS]:
            partes = [c.cliente.nombre if c.cliente else None, c.detalle]
            agregar(CLIENTES, c.fecha_hora, _persona(c.realizado_por), c.get_accion_display(),
                    " · ".join(p for p in partes if p))
        # Pagos y ajustes de cuenta corriente (las compras fiadas ya se ven en el grupo Ventas)
        qs = en_rango(MovimientoCuenta.objects.filter(
            tipo__in=[MovimientoCuenta.PAGO, MovimientoCuenta.AJUSTE]).select_related("cliente", "usuario"))
        if usuario_id:
            qs = qs.filter(usuario_id=usuario_id)
        nombres = dict(Venta.MEDIOS)
        for m in qs[:MAX_EVENTOS]:
            if m.tipo == MovimientoCuenta.PAGO:
                titulo = "Pago de cuenta corriente"
                detalle = f"{m.cliente.nombre} · pagó ${-m.importe} · {nombres.get(m.medio_pago, m.medio_pago)}"
            else:
                titulo = "Ajuste de cuenta corriente"
                signo = "+" if m.importe > 0 else "−"
                detalle = f"{m.cliente.nombre} · {signo}${abs(m.importe)}"
            detalle += f" · quedó debiendo ${m.saldo_resultante}"
            if m.detalle:
                detalle += f" · {m.detalle}"
            agregar(CLIENTES, m.fecha_hora, _persona(m.usuario), titulo, detalle)

    if quiere(GASTOS):
        qs = en_rango(Gasto.objects.select_related("usuario"))
        if usuario_id:
            qs = qs.filter(usuario_id=usuario_id)
        for g in qs[:MAX_EVENTOS]:
            agregar(GASTOS, g.fecha_hora, _persona(g.usuario), "Gasto", f"−${g.monto} · {g.proposito}")
        qs = en_rango(Gasto.objects.filter(anulado=True).select_related("usuario", "anulado_por"), "anulado_en")
        if usuario_id:
            qs = qs.filter(anulado_por_id=usuario_id)
        for g in qs[:MAX_EVENTOS]:
            detalle = f"${g.monto} · {g.proposito} · lo anotó {g.usuario.nombre_completo}"
            if g.motivo_anulacion:
                detalle += f" · {g.motivo_anulacion}"
            agregar(GASTOS, g.anulado_en, _persona(g.anulado_por), "Gasto anulado", detalle)

    if quiere(COMPRAS):
        qs = en_rango(Compra.objects.select_related("comerciante", "producto", "usuario"))
        if usuario_id:
            qs = qs.filter(usuario_id=usuario_id)
        for c in qs[:MAX_EVENTOS]:
            agregar(COMPRAS, c.fecha_hora, _persona(c.usuario), "Compra a comerciante",
                    f"{c.comerciante.nombre} · {c.nombre_producto} · {_texto_cantidad(c.cantidad, c.producto)} · ${c.costo_total}")
        qs = en_rango(PagoCompra.objects.select_related("compra__comerciante", "usuario"))
        if usuario_id:
            qs = qs.filter(usuario_id=usuario_id)
        for p in qs[:MAX_EVENTOS]:
            agregar(COMPRAS, p.fecha_hora, _persona(p.usuario), "Pago a comerciante",
                    f"{p.compra.comerciante.nombre} · ${p.importe} · compra N° {p.compra.numero} ({p.compra.nombre_producto})")
        qs = en_rango(Compra.objects.filter(anulada=True).select_related("comerciante", "anulada_por"), "anulada_en")
        if usuario_id:
            qs = qs.filter(anulada_por_id=usuario_id)
        for c in qs[:MAX_EVENTOS]:
            agregar(COMPRAS, c.anulada_en, _persona(c.anulada_por), "Compra anulada",
                    f"{c.comerciante.nombre} · {c.nombre_producto} · ${c.costo_total} · {c.motivo_anulacion}")

    if quiere(STOCK):
        # Los movimientos de una venta ya se ven en el grupo Ventas: acá van ingresos, pérdidas y recuentos
        qs = en_rango(MovimientoStock.objects.exclude(tipo=MovimientoStock.VENTA).select_related("producto", "usuario"))
        if usuario_id:
            qs = qs.filter(usuario_id=usuario_id)
        for m in qs[:MAX_EVENTOS]:
            signo = "+" if m.cantidad > 0 else "−"
            detalle = f"{m.producto.nombre} · {signo}{_texto_cantidad(m.cantidad, m.producto)}"
            detalle += f" · quedó en {_texto_cantidad(m.stock_resultante, m.producto)}"
            if m.motivo:
                detalle += f" · {m.motivo}"
            agregar(STOCK, m.fecha_hora, _persona(m.usuario), m.get_tipo_display(), detalle)

    if quiere(TURNOS):
        # Correcciones de horario hechas por un dueño
        qs = en_rango(Turno.objects.select_related("usuario", "corregido_por"), "corregido_en")
        if usuario_id:
            qs = qs.filter(corregido_por_id=usuario_id)
        for t in qs[:MAX_EVENTOS]:
            salida = timezone.localtime(t.fin).strftime("%H:%M")
            if t.fin_original and t.fin_original != t.fin:
                antes = timezone.localtime(t.fin_original).strftime("%H:%M")
                titulo, detalle = "Corrección de horario", f"{t.usuario.nombre_completo} · salida {antes} → {salida}"
            else:
                titulo, detalle = "Horario revisado", f"{t.usuario.nombre_completo} · salida {salida}"
            if t.nota:
                detalle += f" · {t.nota}"
            agregar(TURNOS, t.corregido_en, _persona(t.corregido_por), titulo, detalle)

        if not usuario_id:
            # Lo que hizo el sistema solo: cuentas olvidadas y la caja de las 00:45
            for t in en_rango(Turno.objects.filter(tipo_cierre=Turno.SISTEMA).select_related("usuario"), "fin")[:MAX_EVENTOS]:
                agregar(TURNOS, t.fin, SISTEMA, "Cuenta que quedó abierta",
                        f"{t.usuario.nombre_completo} no cerró su cuenta")
            for c in en_rango(CierreDiario.objects.all(), "generado_en")[:MAX_EVENTOS]:
                agregar(TURNOS, c.generado_en, SISTEMA, "Cierre automático del día", f"Día {c.fecha:%d/%m/%Y}")

    eventos.sort(key=lambda e: e["fecha_hora"], reverse=True)

    # Quién tenía el sistema abierto en ese rato (turnos que se cruzan con el rango)
    de_turno = []
    for t in Turno.objects.filter(inicio__lt=hasta).exclude(fin__lte=desde).select_related("usuario__rol").order_by("inicio"):
        de_turno.append({
            "id": t.id, "usuario": {**_persona(t.usuario), "rol": t.usuario.rol.nombre},
            "inicio": t.inicio, "fin": t.fin,
        })

    return {"eventos": eventos[:MAX_EVENTOS], "hay_mas": len(eventos) > MAX_EVENTOS, "de_turno": de_turno}


# ---------- Resultados por sección (RF-51 a RF-54) ----------

def resultados(desde, hasta):
    """Ganancia o pérdida de cada sección entre dos fechas, con el detalle de sus productos.

    Resultado de una sección = lo vendido − lo que costó esa mercadería − las pérdidas (al costo).
    Los gastos no tienen sección: se restan una sola vez, en el resultado del mercado entero.
    Cada producto cuenta en la sección que tiene hoy.
    """
    inicio, fin = rango_de_fechas(desde, hasta)
    cero = Decimal(0)
    secciones = {
        s.nombre: {"id": s.id, "seccion": s.nombre, "ventas": cero, "costo": cero, "perdidas": cero, "productos": {}}
        for s in Seccion.objects.all()
    }

    def fila_de(producto):
        seccion = secciones[producto.categoria.seccion.nombre]
        fila = seccion["productos"].setdefault(producto.id, {
            "id": producto.id, "nombre": producto.nombre, "categoria": producto.categoria.nombre, "unidad": producto.unidad,
            "vendido": cero, "ventas": cero, "costo": cero, "perdido": cero, "perdidas": cero,
        })
        return seccion, fila

    detalles = DetalleVenta.objects.filter(
        venta__fecha_hora__gte=inicio, venta__fecha_hora__lt=fin, venta__anulada=False
    ).select_related("producto__categoria__seccion")
    for d in detalles:
        seccion, fila = fila_de(d.producto)
        costo = (d.cantidad * d.costo_unitario).quantize(CENTAVOS)
        for destino in (seccion, fila):
            destino["ventas"] += d.subtotal
            destino["costo"] += costo
        fila["vendido"] += d.cantidad

    perdidas = MovimientoStock.objects.filter(
        tipo=MovimientoStock.PERDIDA, fecha_hora__gte=inicio, fecha_hora__lt=fin
    ).select_related("producto__categoria__seccion")
    for m in perdidas:
        seccion, fila = fila_de(m.producto)
        valor = abs(m.valor)
        seccion["perdidas"] += valor
        fila["perdidas"] += valor
        fila["perdido"] += abs(m.cantidad)

    def cuentas(d):
        ganancia = d["ventas"] - d["costo"]
        return {"ventas": _dinero(d["ventas"]), "costo": _dinero(d["costo"]), "ganancia_bruta": _dinero(ganancia),
                "perdidas": _dinero(d["perdidas"]), "resultado": _dinero(ganancia - d["perdidas"])}

    lista = []
    total = {"ventas": cero, "costo": cero, "perdidas": cero}
    for s in secciones.values():
        for clave in total:
            total[clave] += s[clave]
        productos = sorted(s["productos"].values(), key=lambda f: f["ventas"] - f["costo"] - f["perdidas"], reverse=True)
        lista.append({
            "id": s["id"], "seccion": s["seccion"], **cuentas(s),
            "productos": [
                {"id": f["id"], "nombre": f["nombre"], "categoria": f["categoria"], "unidad": f["unidad"],
                 "vendido": _cantidad(f["vendido"]), "perdido": _cantidad(f["perdido"]), **cuentas(f)}
                for f in productos
            ],
        })

    gastos = Decimal(resumen_de_gastos(inicio, fin)["total"])
    resultado_secciones = total["ventas"] - total["costo"] - total["perdidas"]

    def primera(clave):
        """Nombre de la sección con el número más alto en `clave`, o None si todas están en cero."""
        mejor = max(lista, key=lambda s: Decimal(s[clave]), default=None)
        return mejor["seccion"] if mejor and Decimal(mejor[clave]) > 0 else None

    return {
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "secciones": lista,
        "general": {
            **cuentas(total),
            "gastos": _dinero(gastos),
            "resultado_secciones": _dinero(resultado_secciones),
            "resultado": _dinero(resultado_secciones - gastos),
        },
        "comparacion": {"vende_mas": primera("ventas"), "gana_mas": primera("resultado"), "pierde_mas": primera("perdidas")},
    }
