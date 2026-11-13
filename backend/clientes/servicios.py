"""Reglas de la cuenta corriente. Las usan la API de clientes y la de ventas.

La deuda de un cliente (`saldo`) solo cambia con `registrar()`, que deja un MovimientoCuenta.
Todas estas funciones deben llamarse dentro de una transacción.
"""

from decimal import Decimal

from .models import Cliente, ConfiguracionCuentas, MovimientoCuenta


class ErrorDeCuenta(Exception):
    """Algo de la cuenta no se puede hacer. El mensaje se le muestra tal cual a la persona."""


def pesos(valor):
    """Decimal → «$ 12.500» o «$ 12.500,50», como se escribe en Argentina."""
    valor = Decimal(valor)
    entero, _, decimales = f"{abs(valor):,.2f}".partition(".")
    texto = entero.replace(",", ".") + ("" if decimales == "00" else f",{decimales}")
    return f"{'−' if valor < 0 else ''}$ {texto}"


def limite_de(cliente, configuracion=None):
    """Tope de deuda que le corresponde: el propio si tiene; si no, el general. None = sin tope."""
    if cliente.limite is not None:
        return cliente.limite
    return (configuracion or ConfiguracionCuentas.actual()).limite_general


def bloquear(cliente_id):
    """Bloquea la fila del cliente mientras dura la operación, para que dos cajas no pisen su deuda."""
    return Cliente.objects.select_for_update().filter(pk=cliente_id).first()


def registrar(cliente, tipo, importe, usuario, venta=None, medio_pago=None, detalle=None):
    """Aplica un movimiento a la cuenta. `cliente` ya tiene que estar bloqueado."""
    cliente.saldo += importe
    cliente.save(update_fields=["saldo"])
    return MovimientoCuenta.objects.create(
        cliente=cliente, tipo=tipo, importe=importe, saldo_resultante=cliente.saldo, venta=venta,
        medio_pago=medio_pago, detalle=(detalle or "").strip()[:200] or None,
        usuario=usuario, turno=getattr(usuario, "turno_abierto", None),
    )


def cliente_para_fiar(cliente_id, total):
    """Devuelve el cliente bloqueado si se le puede fiar `total`. Si no, explica por qué (RF-99, RF-100)."""
    cliente = bloquear(cliente_id) if cliente_id else None
    if cliente is None:
        raise ErrorDeCuenta("Elegí a qué cliente se le anota la compra.")
    if not cliente.activo:
        raise ErrorDeCuenta(f"«{cliente.nombre}» está dado de baja: no se le puede fiar.")
    limite = limite_de(cliente)
    if limite is not None and cliente.saldo + total > limite:
        disponible = max(limite - cliente.saldo, Decimal(0))
        raise ErrorDeCuenta(
            f"No se le puede fiar: «{cliente.nombre}» debe {pesos(cliente.saldo)} y su límite es {pesos(limite)}. "
            f"Le quedan {pesos(disponible)} para fiar. Puede pagar una parte de su deuda o pagar esta compra de otra forma."
        )
    return cliente


def anotar_compra(cliente, venta, usuario):
    return registrar(cliente, MovimientoCuenta.COMPRA, venta.total, usuario, venta=venta,
                     detalle=f"Venta N° {venta.numero}")


def deshacer_compra(venta, usuario, motivo):
    """Una venta fiada se anuló o se modificó: su importe sale de la deuda del cliente."""
    if venta.medio_pago != venta.CUENTA or not venta.cliente_id:
        return None
    cliente = bloquear(venta.cliente_id)
    return registrar(cliente, MovimientoCuenta.ANULACION, -venta.total, usuario, venta=venta, detalle=motivo)
