import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import Encabezado from '../componentes/Encabezado'
import Recibo from '../componentes/Recibo'
import { buscarPorCodigo, imprimirRecibo, leerConfig, useLector } from '../dispositivos'
import { cantidad as textoCantidad, leerNumero, pesos, porUnidad } from '../formato'

// Pantalla de venta del día a día (RF-39, RF-40). La usan todos.
// Se escanea con el lector o se escribe el número o el nombre del producto; el sistema suma solo
// y muestra el total en grande para cobrar. Al cobrar baja el stock y el recibo queda guardado
// (se imprima o no).
//
// La compra se puede cambiar antes de pagar (cantidades, quitar, agregar) y también después:
// «Modificar esta compra» vuelve a abrirla, y el sistema dice cuánto cobrar de más o cuánto devolver.
// También se llega acá desde Recibos con /ventas?corregir=ID.

const MEDIOS = [
  ['EFECTIVO', 'Efectivo'],
  ['DEBITO', 'Débito'],
  ['CREDITO', 'Crédito'],
  ['TRANSFERENCIA', 'Transferencia'],
  ['QR', 'QR'],
  ['CUENTA', 'Cuenta corriente'], // fiado: se anota en la cuenta del cliente
]

const redondear = (n) => Math.round(n * 100) / 100
const aTexto = (n) => String(Number(n)).replace('.', ',')

// Al modificar una compra ya pagada: qué hay que hacer con la plata, según cómo se pagó antes y ahora.
// Lo fiado no se cobra ni se devuelve en el momento: cambia la cuenta del cliente.
function textoDiferencia(medioAntes, medioAhora, totalAntes, totalAhora) {
  const diferencia = redondear(totalAhora - totalAntes)
  const antesFiado = medioAntes === 'CUENTA'
  const ahoraFiado = medioAhora === 'CUENTA'
  if (antesFiado && ahoraFiado) {
    if (diferencia === 0) return 'La cuenta queda igual'
    return diferencia > 0 ? `Se suman ${pesos(diferencia)} a su cuenta` : `Se descuentan ${pesos(-diferencia)} de su cuenta`
  }
  if (antesFiado) return `Cobrar ${pesos(totalAhora)} (sale de su cuenta)`
  if (ahoraFiado) return `Devolver ${pesos(totalAntes)} y anotar ${pesos(totalAhora)} en la cuenta`
  if (diferencia === 0) return 'Sin diferencia'
  return diferencia > 0 ? `Cobrar ${pesos(diferencia)} más` : `Devolver ${pesos(-diferencia)}`
}

// Cantidad válida de un renglón (número mayor a 0; entero si se vende por unidad). null si no sirve.
function cantidadValida(renglon) {
  const n = leerNumero(renglon.cantidad)
  if (n === null || n <= 0) return null
  if (renglon.producto.unidad === 'UNIDAD' && !Number.isInteger(n)) return null
  return n
}

// Arma el carrito con los productos de una venta ya cobrada. Devuelve también los que ya no se pueden vender.
function carritoDe(venta, productos) {
  const carrito = []
  const faltan = []
  for (const item of venta.items) {
    const producto = productos.find((p) => p.id === item.producto)
    if (producto) carrito.push({ producto, cantidad: aTexto(item.cantidad) })
    else faltan.push(item.nombre)
  }
  return { carrito, faltan }
}

export default function Venta() {
  const [params, setParams] = useSearchParams()
  const idCorregir = params.get('corregir')
  const [config] = useState(leerConfig)
  const [productos, setProductos] = useState([])
  const [carrito, setCarrito] = useState([]) // [{ producto, cantidad: texto }]
  const [busqueda, setBusqueda] = useState('')
  const [medio, setMedio] = useState('EFECTIVO')
  const [pagaCon, setPagaCon] = useState('')
  const [clientes, setClientes] = useState([]) // para vender en cuenta corriente
  const [cliente, setCliente] = useState(null) // a quién se le anota la compra fiada
  const [buscaCliente, setBuscaCliente] = useState('')
  const [original, setOriginal] = useState(null) // la venta ya pagada que se está modificando
  const [recibo, setRecibo] = useState(null) // la venta recién cobrada
  const [error, setError] = useState('')
  const [aviso, setAviso] = useState('')
  const [cobrando, setCobrando] = useState(false)
  const buscador = useRef(null)
  const cantidades = useRef({}) // campos de cantidad, por id de producto

  const enfocarBuscador = () => setTimeout(() => buscador.current?.focus(), 0)

  // Vuelve a abrir una compra ya pagada para cambiarla
  const empezarCorreccion = (venta, lista) => {
    const { carrito: armado, faltan } = carritoDe(venta, lista)
    setOriginal(venta)
    setCarrito(armado)
    setMedio(venta.medio_pago)
    setCliente(venta.cliente)
    setBuscaCliente('')
    setPagaCon('')
    setRecibo(null)
    setError('')
    setAviso(faltan.length ? `Ya no se venden y quedaron afuera: ${faltan.join(', ')}.` : '')
    enfocarBuscador()
  }

  // Al entrar: los productos a la venta y, si se viene de Recibos, la compra a modificar
  useEffect(() => {
    let vigente = true
    Promise.all([api('/api/productos/?activo=1'), idCorregir ? api(`/api/ventas/${idCorregir}/`) : null])
      .then(([lista, venta]) => {
        if (!vigente) return
        setProductos(lista)
        if (!venta) return
        if (venta.puede_corregir) empezarCorreccion(venta, lista)
        else setError(`El recibo N° ${venta.numero} ya no se puede modificar${venta.anulada ? ' (está anulado o ya fue modificado)' : ': pedile a un encargado'}.`)
      })
      .catch((err) => vigente && setError(err.status === 404 ? 'Ese recibo no existe.' : err.message))
    return () => { vigente = false }
  }, [idCorregir])

  // Clientes de cuenta corriente, con lo que deben y lo que les queda para fiar
  const cargarClientes = () => api('/api/clientes/?activo=1').then(setClientes).catch(() => {})
  useEffect(() => {
    cargarClientes()
  }, [])

  // Al cobrar, si este equipo está configurado así, el recibo se imprime solo
  useEffect(() => {
    if (recibo && config.imprimirSolo) imprimirRecibo(config.ancho)
  }, [recibo, config])

  const agregar = (producto) => {
    setError('')
    setBusqueda('')
    const porKilo = producto.unidad === 'KG'
    setCarrito((lista) => {
      const existe = lista.find((r) => r.producto.id === producto.id)
      if (!existe) return [...lista, { producto, cantidad: porKilo ? '' : '1' }]
      if (porKilo) return lista // lo pesado se carga a mano: no se suma solo
      return lista.map((r) =>
        r.producto.id === producto.id ? { ...r, cantidad: String((leerNumero(r.cantidad) ?? 0) + 1) } : r,
      )
    })
    // Por kilo hay que escribir el peso: el cursor va a ese campo. Por unidad, vuelve al buscador.
    setTimeout(() => (porKilo ? cantidades.current[producto.id] : buscador.current)?.focus(), 0)
  }

  const texto = busqueda.trim().toLowerCase()
  const sugerencias = texto.length < 2
    ? []
    : productos.filter((p) => p.nombre.toLowerCase().includes(texto) || p.codigo === busqueda.trim()).slice(0, 8)

  // Lo que llega del lector (termina en Enter) o de escribir y apretar Enter
  const procesar = (codigo) => {
    const exacto = buscarPorCodigo(productos, codigo)
    if (exacto) return agregar(exacto)
    const t = codigo.trim().toLowerCase()
    const porNombre = t.length >= 2 ? productos.filter((p) => p.nombre.toLowerCase().includes(t)) : []
    if (porNombre.length === 1) return agregar(porNombre[0])
    if (porNombre.length === 0) {
      setError(`No hay ningún producto a la venta con «${codigo.trim()}». Si es nuevo, hay que cargarlo en Productos.`)
      setBusqueda('')
    }
    // Si hay varios, quedan las sugerencias a la vista para elegir
  }

  const nuevaVenta = () => {
    setRecibo(null)
    setOriginal(null)
    setCarrito([])
    setPagaCon('')
    setMedio('EFECTIVO')
    setCliente(null)
    setBuscaCliente('')
    setError('')
    setAviso('')
    if (idCorregir) setParams({}, { replace: true })
    enfocarBuscador()
  }

  // El lector también funciona cuando el cursor no está en el buscador (por ejemplo, con el recibo en pantalla)
  useLector((codigo) => {
    if (recibo) nuevaVenta()
    procesar(codigo)
  })

  const cambiarCantidad = (id, valor) =>
    setCarrito((lista) => lista.map((r) => (r.producto.id === id ? { ...r, cantidad: valor } : r)))

  const sumar = (renglon, pasos) => {
    const n = Math.max(1, (leerNumero(renglon.cantidad) ?? 0) + pasos)
    cambiarCantidad(renglon.producto.id, String(n))
  }

  const quitar = (id) => {
    setCarrito((lista) => lista.filter((r) => r.producto.id !== id))
    buscador.current?.focus()
  }

  const subtotal = (r) => redondear((cantidadValida(r) ?? 0) * Number(r.producto.precio_venta))
  const total = redondear(carrito.reduce((suma, r) => suma + subtotal(r), 0))
  const listo = carrito.length > 0 && carrito.every((r) => cantidadValida(r) !== null)
  const nPagaCon = leerNumero(pagaCon)

  // Al modificar una compra pagada: cuánto cambió el total (positivo = hay que cobrar más)
  const diferencia = original ? redondear(total - Number(original.total)) : null
  const fiado = medio === 'CUENTA'
  // Datos al día del cliente elegido (deuda y cuánto le queda), y los que coinciden con lo que se busca
  const datosCliente = cliente ? clientes.find((c) => c.id === cliente.id) ?? cliente : null
  const textoCliente = buscaCliente.trim().toLowerCase()
  const clientesVisibles = clientes
    .filter((c) => !textoCliente || c.nombre.toLowerCase().includes(textoCliente) || c.dni === buscaCliente.trim())
    .slice(0, 6)
  // Al modificar una compra fiada del mismo cliente, lo que ya tenía anotado vuelve a estar disponible
  const yaAnotado = original?.medio_pago === 'CUENTA' && original.cliente?.id === cliente?.id ? Number(original.total) : 0
  const disponible = datosCliente?.disponible != null ? redondear(Number(datosCliente.disponible) + yaAnotado) : null
  const pasaElLimite = fiado && disponible !== null && total > disponible

  const sinCambios = Boolean(original) && listo && medio === original.medio_pago &&
    (!fiado || cliente?.id === original.cliente?.id) &&
    carrito.length === original.items.length &&
    carrito.every((r) => original.items.some((i) => i.producto === r.producto.id && Number(i.cantidad) === cantidadValida(r)))

  // Lo que el cliente tiene que pagar ahora: el total, o solo la diferencia si ya había pagado
  // (si la compra anterior era fiada y ahora paga, es el total entero; si ahora es fiada, no paga nada)
  const aPagar = fiado ? 0 : !original ? total : original.medio_pago === 'CUENTA' ? total : Math.max(diferencia, 0)
  const vuelto = medio === 'EFECTIVO' && nPagaCon !== null && aPagar > 0 ? redondear(nPagaCon - aPagar) : null

  const cobrar = async () => {
    setError('')
    if (vuelto !== null && vuelto < 0) return setError('El cliente paga con menos plata de la que tiene que pagar.')
    if (fiado && !cliente) return setError('Elegí a qué cliente se le anota la compra.')
    setCobrando(true)
    try {
      const items = carrito.map((r) => ({ producto: r.producto.id, cantidad: String(cantidadValida(r)) }))
      const idCliente = fiado ? cliente.id : null
      const venta = original
        ? await api(`/api/ventas/${original.id}/corregir/`, { metodo: 'POST', datos: { items, medio_pago: medio, cliente: idCliente } })
        : await api('/api/ventas/', {
            metodo: 'POST',
            datos: {
              items, medio_pago: medio, cliente: idCliente,
              paga_con: medio === 'EFECTIVO' && nPagaCon !== null ? nPagaCon.toFixed(2) : null,
            },
          })
      setRecibo(venta)
      setOriginal(null)
      if (idCorregir) setParams({}, { replace: true })
      api('/api/productos/?activo=1').then(setProductos).catch(() => {}) // el stock cambió
      cargarClientes() // y quizás también la deuda de un cliente
    } catch (err) {
      setError(err.message)
    } finally {
      setCobrando(false)
    }
  }

  // ---------- Después de cobrar: el recibo ----------
  if (recibo) {
    const deudaAhora = recibo.cliente ? clientes.find((c) => c.id === recibo.cliente.id)?.saldo : null
    return (
      <>
        <Encabezado />
        <main className="contenedor venta-cobrada">
          {recibo.corrige_a ? (
            <div className="monto-rosa no-imprimir" role="status">
              <span>Compra modificada · reemplaza al recibo N° {recibo.corrige_a.numero}</span>
              <b>
                {textoDiferencia(recibo.corrige_a.medio_pago, recibo.medio_pago, Number(recibo.corrige_a.total), Number(recibo.total))}
              </b>
              <span>Total nuevo {pesos(recibo.total)} · antes {pesos(recibo.corrige_a.total)}</span>
              {recibo.cliente && <span>Cuenta de {recibo.cliente.nombre}{deudaAhora != null && <> · ahora debe {pesos(deudaAhora)}</>}</span>}
            </div>
          ) : recibo.cliente ? (
            <div className="monto-rosa no-imprimir" role="status">
              <span>Anotado en la cuenta de {recibo.cliente.nombre} · no se cobra ahora</span>
              <b>{pesos(recibo.total)}</b>
              {deudaAhora != null && <span>Ahora debe <b>{pesos(deudaAhora)}</b></span>}
            </div>
          ) : (
            <div className="monto-rosa no-imprimir" role="status">
              <span>Venta cobrada · {recibo.medio_pago_texto}</span>
              <b>{pesos(recibo.total)}</b>
              {recibo.vuelto != null && <span>Vuelto: <b>{pesos(recibo.vuelto)}</b></span>}
            </div>
          )}
          {recibo.avisos.map((a) => <p key={a} className="aviso no-imprimir">{a}</p>)}

          <Recibo venta={recibo} config={config} />

          <div className="botones no-imprimir">
            <button autoFocus onClick={nuevaVenta}>Nueva venta</button>
            <button className="boton-borde" onClick={() => imprimirRecibo(config.ancho)}>Imprimir recibo</button>
            {recibo.puede_corregir && (
              <button className="boton-borde" onClick={() => empezarCorreccion(recibo, productos)}>Modificar esta compra</button>
            )}
            <Link to="/recibos" className="boton boton-secundario">Ver recibos</Link>
          </div>
          <p className="texto-suave no-imprimir">
            El recibo ya quedó guardado, se imprima o no. Podés escanear el próximo producto directamente: empieza una venta nueva.
          </p>
        </main>
      </>
    )
  }

  // ---------- Armando la venta ----------
  return (
    <>
      <Encabezado />
      <main className="contenedor">
        <div className="titulo-con-accion">
          <div>
            <h1>{original ? `Modificar la compra N° ${original.numero}` : 'Venta'}</h1>
            <p className="subtitulo">
              {original
                ? 'Agregá, sacá o cambiá productos. El sistema calcula la diferencia.'
                : 'Escaneá los productos o escribí el número o el nombre'}
            </p>
          </div>
          <Link to="/recibos" className="boton boton-secundario">Ver recibos</Link>
        </div>

        {original && (
          <p className="aviso">
            Estás modificando una compra ya pagada ({pesos(original.total)}, {original.medio_pago_texto}). El recibo anterior
            queda guardado como reemplazado. <button className="boton-texto" onClick={nuevaVenta}>Dejarla como estaba</button>
          </p>
        )}
        {aviso && <p className="aviso">{aviso}</p>}

        <div className="venta">
          <section>
            <input
              ref={buscador}
              className="buscador buscador-venta"
              value={busqueda}
              autoFocus
              autoComplete="off"
              placeholder="Código de barras, número o nombre del producto"
              onChange={(e) => { setBusqueda(e.target.value); setError('') }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && busqueda.trim()) {
                  e.preventDefault()
                  procesar(busqueda)
                }
              }}
            />

            {sugerencias.length > 0 && (
              <ul className="sugerencias">
                {sugerencias.map((p) => (
                  <li key={p.id}>
                    <button className="boton-borde" onClick={() => agregar(p)}>
                      <span>
                        <span className={`punto punto-${p.semaforo.toLowerCase()}`} /> {p.nombre}
                        {p.codigo && <small className="texto-suave"> · N° {p.codigo}</small>}
                      </span>
                      <b>{pesos(p.precio_venta)} <small>{porUnidad(p)}</small></b>
                    </button>
                  </li>
                ))}
              </ul>
            )}

            {error && <p className="mensaje-error" role="alert">{error}</p>}

            {carrito.length === 0 ? (
              <p className="subtitulo carrito-vacio">Todavía no hay productos en esta venta.</p>
            ) : (
              <ul className="lista-usuarios">
                {carrito.map((r) => {
                  const p = r.producto
                  const valida = cantidadValida(r) !== null
                  return (
                    <li key={p.id} className="tarjeta renglon-venta">
                      <div className="datos-usuario">
                        <strong>{p.nombre}</strong>
                        <span className="texto-suave">
                          {pesos(p.precio_venta)} {porUnidad(p)}
                          {Number(p.stock_actual) <= 0 && <span className="etiqueta etiqueta-roja">Sin stock en el sistema</span>}
                        </span>
                      </div>

                      <div className="cantidad-venta">
                        {p.unidad === 'UNIDAD' && (
                          <button className="boton-chico boton-borde" aria-label="Uno menos" onClick={() => sumar(r, -1)}>−</button>
                        )}
                        <input
                          ref={(el) => { cantidades.current[p.id] = el }}
                          className={valida ? '' : 'campo-invalido'}
                          value={r.cantidad}
                          inputMode="decimal"
                          autoComplete="off"
                          aria-label={`Cantidad de ${p.nombre}`}
                          placeholder={p.unidad === 'KG' ? 'kg' : ''}
                          onChange={(e) => cambiarCantidad(p.id, e.target.value)}
                          onFocus={(e) => e.target.select()}
                          onKeyDown={(e) => { if (e.key === 'Enter') buscador.current?.focus() }}
                        />
                        {p.unidad === 'UNIDAD' ? (
                          <button className="boton-chico boton-borde" aria-label="Uno más" onClick={() => sumar(r, 1)}>+</button>
                        ) : (
                          <span className="texto-suave">kg</span>
                        )}
                      </div>

                      <b className="subtotal-venta">{valida ? pesos(subtotal(r)) : '—'}</b>
                      <button className="boton-texto" onClick={() => quitar(p.id)}>Quitar</button>
                    </li>
                  )
                })}
              </ul>
            )}
          </section>

          <aside className="tarjeta cobro">
            <span className="texto-suave">{original ? 'Total nuevo' : 'Total a cobrar'}</span>
            <b className="total-venta" aria-live="polite">{pesos(total)}</b>
            <small className="texto-suave">
              {carrito.length} {carrito.length === 1 ? 'producto' : 'productos'}
              {carrito.some((r) => r.producto.unidad === 'UNIDAD') &&
                <> · {textoCantidad(carrito.filter((r) => r.producto.unidad === 'UNIDAD').reduce((s, r) => s + (cantidadValida(r) ?? 0), 0), 'UNIDAD')}</>}
            </small>

            {original && (
              <div className="diferencia">
                <span className="texto-suave">
                  {original.medio_pago === 'CUENTA' ? `Tenía anotados ${pesos(original.total)}` : `Ya pagó ${pesos(original.total)}`}
                </span>
                <b>{textoDiferencia(original.medio_pago, medio, Number(original.total), total)}</b>
              </div>
            )}

            <fieldset className="grupo">
              <legend>¿Cómo paga?</legend>
              <div className="opciones-fila">
                {MEDIOS.map(([valor, nombre]) => (
                  <button type="button" key={valor} className={`opcion-boton ${medio === valor ? 'elegida' : ''}`}
                    aria-pressed={medio === valor} onClick={() => setMedio(valor)}>
                    {nombre}
                  </button>
                ))}
              </div>
            </fieldset>

            {fiado && (
              <div className="cliente-venta">
                {cliente ? (
                  <>
                    <span className="texto-suave">Se anota en la cuenta de</span>
                    <b>{cliente.nombre}</b>
                    {datosCliente?.saldo != null && (
                      <small className="texto-suave">
                        Hoy debe {pesos(datosCliente.saldo)}
                        {disponible !== null ? <> · le quedan {pesos(disponible)} para fiar</> : ' · sin límite'}
                      </small>
                    )}
                    {pasaElLimite && (
                      <span className="error-campo">
                        Con esta compra pasa su límite. Puede pagar una parte de su deuda o pagar de otra forma.
                      </span>
                    )}
                    <button className="boton-texto" onClick={() => { setCliente(null); setBuscaCliente('') }}>Cambiar de cliente</button>
                  </>
                ) : (
                  <>
                    <label>
                      ¿A qué cliente se le anota?
                      <input value={buscaCliente} autoComplete="off" placeholder="Buscar por nombre o DNI"
                        onChange={(e) => setBuscaCliente(e.target.value)} />
                    </label>
                    {clientesVisibles.map((c) => (
                      <button key={c.id} className="boton-borde opcion-cliente" onClick={() => { setCliente(c); setError('') }}>
                        <span>{c.nombre}</span>
                        <small>{Number(c.saldo) > 0 ? `debe ${pesos(c.saldo)}` : 'no debe nada'}</small>
                      </button>
                    ))}
                    {clientesVisibles.length === 0 && (
                      <small className="texto-suave">
                        {clientes.length === 0 ? 'Todavía no hay clientes cargados.' : 'Ningún cliente coincide.'}{' '}
                        Los clientes se cargan en <Link to="/clientes">Cuentas corrientes</Link>.
                      </small>
                    )}
                  </>
                )}
              </div>
            )}

            {medio === 'EFECTIVO' && aPagar > 0 && (
              <label>
                Paga con <small>(opcional, para calcular el vuelto)</small>
                <input value={pagaCon} inputMode="decimal" autoComplete="off" placeholder="Ej.: 20000"
                  onChange={(e) => { setPagaCon(e.target.value); setError('') }} />
                {vuelto !== null && (
                  <span className={vuelto < 0 ? 'error-campo' : 'vuelto'}>
                    {vuelto < 0 ? `Faltan ${pesos(-vuelto)}` : <>Vuelto: <b>{pesos(vuelto)}</b></>}
                  </span>
                )}
              </label>
            )}

            <button className="boton-cobrar" disabled={!listo || cobrando || sinCambios || (fiado && (!cliente || pasaElLimite))} onClick={cobrar}>
              {cobrando ? 'Guardando…' : original ? 'Guardar la compra modificada' : fiado ? `Anotar ${pesos(total)} en la cuenta` : `Cobrar ${pesos(total)}`}
            </button>
            {carrito.length > 0 && !listo && (
              <small className="error-campo">Revisá las cantidades marcadas (lo que va por kilo necesita el peso).</small>
            )}
            {sinCambios && <small className="texto-suave">Todavía no cambiaste nada de la compra.</small>}
            {original && carrito.length === 0 && (
              <small className="texto-suave">Para devolver toda la compra, un encargado la anula desde Recibos.</small>
            )}
            {carrito.length > 0 && (
              <button className="boton-texto" onClick={nuevaVenta}>{original ? 'Dejarla como estaba' : 'Vaciar la venta'}</button>
            )}
          </aside>
        </div>
      </main>
    </>
  )
}
