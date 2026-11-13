import { useEffect, useState } from 'react'
import { api } from '../api'
import ConfirmarBaja from '../componentes/ConfirmarBaja'
import Encabezado from '../componentes/Encabezado'
import { cantidad as textoCantidad, fechaHora, leerNumero, pesos, porUnidad } from '../formato'
import ProductoNuevoRapido from '../componentes/ProductoNuevoRapido'
import { PRODUCTO_VACIO, unidadDe } from '../productoNuevo'
import { llegaEnBultos, nombrePresentacion, PRESENTACIONES } from '../presentaciones'

// Compras a comerciantes (RF-112 a RF-119). Solo dueños y encargados.
// Cada renglón es un producto que se le compró a un comerciante: cantidad, costo, fecha y hora
// (las pone el sistema) y cómo va el pago. El color lo dice todo:
//   verde = pagado completo · amarillo = falta pagar una parte · rojo = todavía no se pagó.

const MEDIOS = [
  ['EFECTIVO', 'Efectivo'],
  ['TRANSFERENCIA', 'Transferencia'],
  ['DEBITO', 'Débito'],
  ['CREDITO', 'Crédito'],
  ['QR', 'QR'],
]

// Cómo se paga al anotar la compra, y el color de cada estado
const FORMAS = [
  ['TODO', 'Se pagó todo', 'verde'],
  ['PARTE', 'Se pagó una parte', 'amarillo'],
  ['NADA', 'Todavía no se pagó', 'rojo'],
]
const COLOR = { PAGADO: 'verde', PARCIAL: 'amarillo', DEBE: 'rojo' }
const FILTROS = [[null, 'Todas'], ['DEBE', 'Sin pagar'], ['PARCIAL', 'Falta una parte'], ['PAGADO', 'Pagadas']]

const VACIO = {
  comerciante: '', presentacion: 'SUELTO', cantidad: '', bultos: '', contenido: '', costo: '', forma: 'NADA', pagado: '',
  medio: 'EFECTIVO', sumarStock: true, nota: '',
}
const aTexto = (n) => String(Number(n)).replace('.', ',')

export default function Compras() {
  const [datos, setDatos] = useState(null) // { deuda_total, comerciantes, compras }
  const [productos, setProductos] = useState([])
  const [estado, setEstado] = useState(null)
  const [comercianteId, setComercianteId] = useState('')
  const [form, setForm] = useState(VACIO)
  const [productoElegido, setProducto] = useState(null)
  const [buscaProducto, setBuscaProducto] = useState('')
  // Si lo que se compró todavía no existe, se crea acá mismo y queda en Productos y en Stock (RF-122)
  const [nuevo, setNuevo] = useState(null) // null = se eligió uno que ya existe
  const [secciones, setSecciones] = useState([])
  // Para las cuentas del formulario: el producto elegido o, si es nuevo, lo que se sabe de él
  const producto = nuevo
    ? { id: null, nombre: nuevo.nombre, unidad: unidadDe(nuevo, secciones), presentacion: 'SUELTO', contenido: null }
    : productoElegido
  const [errores, setErrores] = useState({})
  const [panel, setPanel] = useState(null) // { tipo: 'pago' | 'anular', id }
  const [pago, setPago] = useState({ importe: '', medio: 'EFECTIVO' })
  const [enviando, setEnviando] = useState(false)
  const [aviso, setAviso] = useState('')
  const [error, setError] = useState('')

  const ruta = `/api/compras/?${new URLSearchParams({ ...(estado && { estado }), ...(comercianteId && { comerciante: comercianteId }) })}`
  const cargar = () => api(ruta).then(setDatos)

  useEffect(() => {
    let vigente = true
    api(ruta).then((d) => vigente && setDatos(d)).catch((err) => vigente && setError(err.message))
    return () => { vigente = false }
  }, [ruta])

  const cargarProductos = () => api('/api/productos/?activo=1').then(setProductos).catch(() => {})
  useEffect(() => {
    cargarProductos()
    api('/api/secciones/').then(setSecciones).catch(() => {})
  }, [])

  const agregarCategoria = (c) =>
    setSecciones((lista) => lista.map((s) => (s.id === c.seccion ? { ...s, categorias: [...s.categorias, c] } : s)))

  const cambiar = (campo, valor) => {
    setForm((f) => ({ ...f, [campo]: valor }))
    setErrores((e) => ({ ...e, [campo]: undefined }))
  }

  // Al elegir el producto: si en Productos dice que llega en cajón (o caja, bandeja…), se propone eso
  const elegirProducto = (p) => {
    setProducto(p)
    setErrores((e) => ({ ...e, producto: undefined }))
    if (llegaEnBultos(p)) setForm((f) => ({ ...f, presentacion: p.presentacion, contenido: aTexto(p.contenido) }))
  }

  const elegirPresentacion = (valor) => {
    // Si es la misma en la que llega el producto, ya se sabe cuánto trae cada una
    const conocido = producto && producto.presentacion === valor && llegaEnBultos(producto) ? aTexto(producto.contenido) : ''
    setForm((f) => ({ ...f, presentacion: valor, contenido: valor === 'SUELTO' ? '' : conocido || f.contenido }))
    setErrores((e) => ({ ...e, cantidad: undefined, bultos: undefined, contenido: undefined }))
  }

  // Se compra suelto (por kilo o unidad) o por caja, cajón, bandeja…: ahí el total lo calcula el sistema
  const porBulto = form.presentacion !== 'SUELTO'
  const nBultos = leerNumero(form.bultos)
  const nContenido = leerNumero(form.contenido)
  const nCantidad = porBulto ? (nBultos > 0 && nContenido > 0 ? Math.round(nBultos * nContenido * 1000) / 1000 : null) : leerNumero(form.cantidad)
  const unBulto = nombrePresentacion(form.presentacion)
  const variosBultos = nombrePresentacion(form.presentacion, 2)
  const medida = producto?.unidad === 'KG' ? 'kilos' : 'unidades'
  const nCosto = leerNumero(form.costo)
  const nPagado = form.forma === 'TODO' ? nCosto : form.forma === 'PARTE' ? leerNumero(form.pagado) : 0
  const unitario = nCantidad > 0 && nCosto > 0 ? nCosto / nCantidad : null

  const textoProducto = buscaProducto.trim().toLowerCase()
  const productosVisibles = textoProducto.length < 2
    ? []
    : productos.filter((p) => p.nombre.toLowerCase().includes(textoProducto) || p.codigo === buscaProducto.trim() || p.codigo_barras === buscaProducto.trim()).slice(0, 6)

  const anotar = async (e) => {
    e.preventDefault()
    setError('')
    setAviso('')
    const errs = {}
    if (form.comerciante.trim().length < 2) errs.comerciante = 'Escribí a quién se le compró.'
    const nVenta = nuevo ? leerNumero(nuevo.venta) : null
    const errsNuevo = {}
    if (nuevo) {
      if (nuevo.nombre.trim().length < 2) errsNuevo.nombre = 'Escribí el nombre del producto.'
      if (!nuevo.seccionId) errsNuevo.seccion = 'Elegí la sección.'
      else if (!nuevo.categoria) errsNuevo.categoria = 'Elegí una categoría.'
      if (nVenta === null || nVenta <= 0) errsNuevo.precio_venta = 'Escribí a cuánto se va a vender.'
      if (Object.keys(errsNuevo).length) errs.producto_nuevo = errsNuevo
    } else if (!producto) errs.producto = 'Elegí el producto que se compró.'
    if (porBulto) {
      if (nBultos === null || nBultos <= 0) errs.bultos = `Escribí cuántos ${variosBultos} se compraron.`
      if (nContenido === null || nContenido <= 0) errs.contenido = `Escribí cuánto trae cada ${unBulto}, aunque sea aproximado.`
      else if (producto?.unidad === 'UNIDAD' && !Number.isInteger(nContenido)) errs.contenido = 'Va por unidad: tiene que ser un número entero.'
      else if (producto?.unidad === 'UNIDAD' && nCantidad !== null && !Number.isInteger(nCantidad)) errs.bultos = 'El total tiene que dar un número entero de unidades.'
    } else if (nCantidad === null || nCantidad <= 0) errs.cantidad = 'Escribí la cantidad, con números.'
    else if (producto?.unidad === 'UNIDAD' && !Number.isInteger(nCantidad)) errs.cantidad = 'Va por unidad: tiene que ser un número entero.'
    if (nCosto === null || nCosto <= 0) errs.costo = 'Escribí cuánto costó, con números.'
    if (form.forma === 'PARTE') {
      if (nPagado === null || nPagado <= 0) errs.pagado = 'Escribí cuánto se pagó.'
      else if (nCosto !== null && nPagado >= nCosto) errs.pagado = 'Si se pagó todo, elegí «Se pagó todo».'
    }
    setErrores(errs)
    if (Object.keys(errs).length) return

    setEnviando(true)
    try {
      const c = await api('/api/compras/', {
        metodo: 'POST',
        datos: {
          comerciante: form.comerciante, costo_total: nCosto.toFixed(2),
          ...(nuevo
            ? { producto_nuevo: { nombre: nuevo.nombre, categoria: Number(nuevo.categoria), unidad: producto.unidad, precio_venta: nVenta.toFixed(2) } }
            : { producto: producto.id }),
          ...(porBulto
            ? { presentacion: form.presentacion, bultos: String(nBultos), contenido: String(nContenido) }
            : { presentacion: 'SUELTO', cantidad: String(nCantidad) }),
          pagado: (nPagado ?? 0).toFixed(2), medio_pago: form.medio, sumar_stock: form.sumarStock, nota: form.nota,
        },
      })
      setAviso(`Anotado: ${c.presentacion_texto ? `${c.presentacion_texto} = ` : ''}${textoCantidad(c.cantidad, c.unidad)} de ${c.nombre_producto} a ${c.comerciante_nombre} por ${pesos(c.costo_total)} · ${c.estado_texto.toLowerCase()}.`)
      if (nuevo) {
        setAviso((a) => `${a} «${c.nombre_producto}» quedó cargado como producto nuevo: ya aparece en Productos y en Stock.`)
        cargarProductos()
      }
      setForm({ ...VACIO, comerciante: form.comerciante }) // suele venir más de un producto del mismo comerciante
      setProducto(null)
      setNuevo(null)
      setBuscaProducto('')
      await cargar()
    } catch (err) {
      if (err.status === 400 && err.datos && !err.datos.detail) setErrores({ ...err.datos, costo: err.datos.costo_total })
      else setError(err.message)
    } finally {
      setEnviando(false)
    }
  }

  const abrir = (tipo, c) => {
    setError('')
    setAviso('')
    setPanel({ tipo, id: c.id })
    if (tipo === 'pago') setPago({ importe: String(Number(c.falta)).replace('.', ','), medio: 'EFECTIVO' })
  }

  const pagar = async (e, c) => {
    e.preventDefault()
    const importe = leerNumero(pago.importe)
    if (importe === null || importe <= 0) return setError('Escribí cuánto se paga, con números.')
    if (importe > Number(c.falta)) return setError(`Solo faltan pagar ${pesos(c.falta)}: no se puede pagar más que eso.`)
    setEnviando(true)
    setError('')
    try {
      const nueva = await api(`/api/compras/${c.id}/pago/`, { metodo: 'POST', datos: { importe: importe.toFixed(2), medio_pago: pago.medio } })
      setPanel(null)
      setAviso(`Se anotó el pago de ${pesos(importe)} a ${c.comerciante_nombre}: ${nueva.estado === 'PAGADO' ? 'la compra quedó pagada' : `faltan ${pesos(nueva.falta)}`}.`)
      await cargar()
    } catch (err) {
      setError(err.message)
    } finally {
      setEnviando(false)
    }
  }

  const anular = async (c, motivo) => {
    setError('')
    if (!motivo.trim()) return setError('Indicá el motivo de la anulación.')
    try {
      await api(`/api/compras/${c.id}/anular/`, { metodo: 'POST', datos: { motivo } })
      setPanel(null)
      setAviso(`Se anuló la compra de ${c.nombre_producto} a ${c.comerciante_nombre}.${c.sumo_stock ? ' La mercadería que había sumado se descontó del stock.' : ''}`)
      await cargar()
    } catch (err) {
      setError(err.message)
    }
  }

  const errorDe = (campo) => errores[campo] && <span className="error-campo">{[errores[campo]].flat().join(' ')}</span>
  const compras = datos?.compras ?? []
  const conDeuda = datos?.comerciantes.filter((c) => Number(c.deuda) > 0) ?? []

  return (
    <>
      <Encabezado />
      <main className="contenedor">
        <h1>Compras a comerciantes</h1>
        <p className="subtitulo">Lo que se les compra a los comerciantes: producto, cantidad, costo y cómo va el pago</p>

        <form className="tarjeta panel-cuenta" onSubmit={anotar} noValidate>
          <strong>Anotar una compra</strong>
          <div className="fila-precios">
            <label>
              Comerciante
              <input value={form.comerciante} maxLength={100} list="lista-comerciantes" autoComplete="off"
                placeholder="A quién se le compró" onChange={(e) => cambiar('comerciante', e.target.value)} />
              <datalist id="lista-comerciantes">
                {datos?.comerciantes.map((c) => <option key={c.id} value={c.nombre} />)}
              </datalist>
              {errorDe('comerciante')}
            </label>

            <div className="grupo">
              <span className="etiqueta-campo">Producto</span>
              {nuevo ? (
                <div className="producto-elegido">
                  <span><b>Producto nuevo</b> <small className="texto-suave">completá sus datos acá abajo</small></span>
                  <button type="button" className="boton-texto" onClick={() => { setNuevo(null); setErrores({}) }}>Elegir uno que ya existe</button>
                </div>
              ) : producto ? (
                <div className="producto-elegido">
                  <span><b>{producto.nombre}</b> <small className="texto-suave">{producto.seccion} · se cuenta {producto.unidad === 'KG' ? 'por kilo' : 'por unidad'}</small></span>
                  <button type="button" className="boton-texto" onClick={() => { setProducto(null); setBuscaProducto('') }}>Cambiar</button>
                </div>
              ) : (
                <>
                  <input value={buscaProducto} autoComplete="off" placeholder="Buscar por nombre o código"
                    onChange={(e) => { setBuscaProducto(e.target.value); setErrores({ ...errores, producto: undefined }) }}
                    onKeyDown={(e) => { if (e.key === 'Enter') e.preventDefault() }} />
                  {productosVisibles.map((p) => (
                    <button type="button" key={p.id} className="boton-borde opcion-cliente" onClick={() => elegirProducto(p)}>
                      <span>{p.nombre}</span>
                      <small>{p.seccion}</small>
                    </button>
                  ))}
                  {textoProducto.length >= 2 && productosVisibles.length === 0 && (
                    <small className="texto-suave">No hay ningún producto con ese nombre.</small>
                  )}
                  <button type="button" className="boton-texto crear-producto"
                    onClick={() => { setNuevo({ ...PRODUCTO_VACIO, nombre: buscaProducto.trim() }); setErrores({}) }}>
                    + Es un producto nuevo{buscaProducto.trim() && `: crear «${buscaProducto.trim()}»`}
                  </button>
                </>
              )}
              {errorDe('producto')}
            </div>

          </div>

          {nuevo && (
            <>
              <ProductoNuevoRapido valor={nuevo} onCambiar={(v) => { setNuevo(v); setErrores((e) => ({ ...e, producto_nuevo: undefined })) }}
                secciones={secciones} onNuevaCategoria={agregarCategoria} errores={errores.producto_nuevo ?? {}}
                costoConocido={unitario ?? undefined} />
              <small className="texto-suave">
                Se guarda también en Productos y en Stock. Su costo queda en lo que salió en esta compra{unitario !== null && <> ({pesos(unitario)} {porUnidad(producto)})</>}.
              </small>
            </>
          )}

          <fieldset className="grupo">
            <legend>¿En qué se compró?</legend>
            <div className="opciones-fila">
              {PRESENTACIONES.map(([valor, nombre]) => (
                <button type="button" key={valor} aria-pressed={form.presentacion === valor}
                  className={`opcion-boton opcion-chica ${form.presentacion === valor ? 'elegida' : ''}`}
                  onClick={() => elegirPresentacion(valor)}>
                  {valor === 'SUELTO' ? (producto ? (producto.unidad === 'KG' ? 'Por kilo' : 'Por unidad') : 'Por kilo o unidad') : nombre}
                </button>
              ))}
            </div>
          </fieldset>

          <div className="fila-precios">
            {porBulto ? (
              <>
                <label>
                  ¿{['CAJA', 'BANDEJA', 'BOLSA'].includes(form.presentacion) ? 'Cuántas' : 'Cuántos'} {variosBultos}?
                  <input value={form.bultos} inputMode="decimal" autoComplete="off" placeholder="Ej.: 2" onChange={(e) => cambiar('bultos', e.target.value)} />
                  {errorDe('bultos')}
                </label>
                <label>
                  ¿Cuánto trae cada {unBulto}? <small>({producto ? `en ${medida}` : 'kilos o unidades'}, puede ser aproximado)</small>
                  <input value={form.contenido} inputMode="decimal" autoComplete="off" placeholder={producto?.unidad === 'UNIDAD' ? 'Ej.: 12' : 'Ej.: 18'}
                    onChange={(e) => cambiar('contenido', e.target.value)} />
                  {nCantidad !== null && producto && (
                    <small className="texto-suave">Son {textoCantidad(nCantidad, producto.unidad)} en total: eso se suma al stock</small>
                  )}
                  {errorDe('contenido')}
                </label>
              </>
            ) : (
              <label>
                Cantidad {producto && <small>({producto.unidad === 'KG' ? 'en kilos' : 'en unidades'})</small>}
                <input value={form.cantidad} inputMode="decimal" autoComplete="off" onChange={(e) => cambiar('cantidad', e.target.value)} />
                {errorDe('cantidad')}
              </label>
            )}

            <label>
              Costo total <small>(lo que costó todo)</small>
              <input value={form.costo} inputMode="decimal" autoComplete="off" placeholder="Ej.: 80000" onChange={(e) => cambiar('costo', e.target.value)} />
              {nCosto > 0 && (porBulto ? nBultos > 0 : unitario !== null && producto) && (
                <small className="texto-suave">
                  Sale{porBulto && <> {pesos(nCosto / nBultos)} cada {unBulto}</>}
                  {unitario !== null && producto && <>{porBulto && ' ·'} {pesos(unitario)} {porUnidad(producto)}</>}
                </small>
              )}
              {errorDe('costo')}
            </label>
          </div>

          <fieldset className="grupo">
            <legend>¿Cómo quedó el pago?</legend>
            <div className="opciones-fila">
              {FORMAS.map(([valor, texto, color]) => (
                <button type="button" key={valor} aria-pressed={form.forma === valor}
                  className={`opcion-boton opcion-pago opcion-pago-${color} ${form.forma === valor ? 'elegida' : ''}`}
                  onClick={() => cambiar('forma', valor)}>
                  {texto}
                </button>
              ))}
            </div>
          </fieldset>

          {form.forma !== 'NADA' && (
            <div className="fila-precios">
              {form.forma === 'PARTE' && (
                <label>
                  ¿Cuánto se pagó?
                  <input value={form.pagado} inputMode="decimal" autoComplete="off" onChange={(e) => cambiar('pagado', e.target.value)} />
                  {nCosto > 0 && nPagado > 0 && nPagado < nCosto && <small className="texto-suave">Quedan por pagar {pesos(nCosto - nPagado)}</small>}
                  {errorDe('pagado')}
                </label>
              )}
              <label>
                ¿Con qué se pagó?
                <select value={form.medio} onChange={(e) => cambiar('medio', e.target.value)}>
                  {MEDIOS.map(([valor, texto]) => <option key={valor} value={valor}>{texto}</option>)}
                </select>
              </label>
            </div>
          )}

          <label className="permiso-usuario">
            <input type="checkbox" className="casilla" checked={form.sumarStock} onChange={(e) => cambiar('sumarStock', e.target.checked)} />
            Sumar esta mercadería al stock <small className="texto-suave">(destildalo si ya la cargaste en Stock)</small>
          </label>

          <div className="botones">
            <button type="submit" disabled={enviando}>{enviando ? 'Anotando…' : 'Anotar la compra'}</button>
          </div>
        </form>

        {aviso && (
          <p className="mensaje-ok" role="status">
            {aviso} <button className="boton-texto" onClick={() => setAviso('')}>Cerrar</button>
          </p>
        )}
        {error && <p className="mensaje-error" role="alert">{error}</p>}

        {datos && (
          <div className="tarjeta vendido-hoy">
            <div>
              <small className="texto-suave">Se les debe a los comerciantes</small>
              <b className={Number(datos.deuda_total) > 0 ? 'texto-rojo' : ''}>{pesos(datos.deuda_total)}</b>
            </div>
            {conDeuda.map((c) => (
              <div key={c.id}>
                <small className="texto-suave">{c.nombre}</small>
                <span>{pesos(c.deuda)}</span>
              </div>
            ))}
          </div>
        )}

        <div className="filtros">
          <div className="chips" role="tablist" aria-label="Estado del pago">
            {FILTROS.map(([valor, texto]) => (
              <button key={texto} role="tab" aria-selected={estado === valor} onClick={() => setEstado(valor)}>
                {valor && <span className={`punto punto-${COLOR[valor]}`} />} {texto}
              </button>
            ))}
          </div>
          {datos && datos.comerciantes.length > 1 && (
            <select className="filtro-comerciante" value={comercianteId} aria-label="Comerciante" onChange={(e) => setComercianteId(e.target.value)}>
              <option value="">Todos los comerciantes</option>
              {datos.comerciantes.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
            </select>
          )}
        </div>

        {datos === null ? (
          <p className="subtitulo">Cargando…</p>
        ) : compras.length === 0 ? (
          <p className="subtitulo">{estado || comercianteId ? 'Ninguna compra coincide.' : 'Todavía no se anotó ninguna compra.'}</p>
        ) : (
          <ul className="lista-usuarios">
            {compras.map((c) => {
              const color = c.anulada ? 'gris' : COLOR[c.estado]
              return (
                <li key={c.id} className={`tarjeta fila-usuario borde-${color} ${c.anulada ? 'compra-anulada' : ''}`}>
                  <div className="datos-usuario">
                    <strong>
                      {c.nombre_producto} · {c.presentacion_texto
                        ? `${Number(c.bultos).toLocaleString('es-AR')} ${nombrePresentacion(c.presentacion, Number(c.bultos))}`
                        : textoCantidad(c.cantidad, c.unidad)}
                      <span className={`etiqueta estado-pago estado-pago-${color}`}>{c.anulada ? 'Anulada' : c.estado_texto}</span>
                    </strong>
                    {c.presentacion_texto && (
                      <span>{c.presentacion_texto} = <b>{textoCantidad(c.cantidad, c.unidad)}</b></span>
                    )}
                    <span>Comerciante: <b>{c.comerciante_nombre}</b></span>
                    <span className="texto-suave">
                      {fechaHora(c.fecha_hora)} · anotó {c.usuario} · {c.seccion}
                      {!c.sumo_stock && ' · no sumó al stock'}
                    </span>
                    {c.pagos.length > 0 && (
                      <small className="texto-suave">
                        Pagos: {c.pagos.map((p) => `${pesos(p.importe)} (${p.medio_pago_texto.toLowerCase()}, ${fechaHora(p.fecha_hora)})`).join(' · ')}
                      </small>
                    )}
                    {c.anulada && <small className="texto-suave">Anulada por {c.anulada_por}: {c.motivo_anulacion}</small>}
                  </div>

                  <div className="stock-cantidad">
                    <b className="saldo-cliente">{pesos(c.costo_total)}</b>
                    <small className="texto-suave">
                      {c.costo_bulto != null && <>{pesos(c.costo_bulto)} cada {nombrePresentacion(c.presentacion)} · </>}
                      {pesos(c.costo_unitario)} {c.unidad === 'KG' ? '/ kg' : 'c/u'}
                    </small>
                    {!c.anulada && c.estado !== 'PAGADO' && (
                      <small className={`texto-${color}`}>
                        {c.estado === 'PARCIAL' && <>pagado {pesos(c.pagado)} · </>}falta {pesos(c.falta)}
                      </small>
                    )}
                  </div>

                  {!c.anulada && (
                    <div className="botones botones-stock">
                      {c.estado !== 'PAGADO' && <button className="boton-chico" onClick={() => abrir('pago', c)}>Anotar un pago</button>}
                      <button className="boton-chico boton-texto" onClick={() => abrir('anular', c)}>Anular</button>
                    </div>
                  )}

                  {panel?.tipo === 'pago' && panel.id === c.id && (
                    <form className="panel-stock" onSubmit={(e) => pagar(e, c)} noValidate>
                      <strong>Pago a {c.comerciante_nombre}</strong>
                      <div className="fila-precios">
                        <label>
                          ¿Cuánto se paga? <small>(faltan {pesos(c.falta)})</small>
                          <input value={pago.importe} inputMode="decimal" autoComplete="off" autoFocus
                            onFocus={(e) => e.target.select()} onChange={(e) => setPago({ ...pago, importe: e.target.value })} />
                        </label>
                        <label>
                          ¿Con qué se paga?
                          <select value={pago.medio} onChange={(e) => setPago({ ...pago, medio: e.target.value })}>
                            {MEDIOS.map(([valor, texto]) => <option key={valor} value={valor}>{texto}</option>)}
                          </select>
                        </label>
                      </div>
                      <div className="botones">
                        <button type="submit" disabled={enviando}>{enviando ? 'Guardando…' : 'Guardar el pago'}</button>
                        <button type="button" className="boton-secundario" onClick={() => setPanel(null)}>Cancelar</button>
                      </div>
                    </form>
                  )}

                  {panel?.tipo === 'anular' && panel.id === c.id && (
                    <ConfirmarBaja
                      textoBoton="Sí, anular"
                      mensaje={<>¿Anular la compra de <b>{c.nombre_producto}</b> a {c.comerciante_nombre}? Escribí el motivo.{c.sumo_stock && ' La mercadería que sumó se descuenta del stock.'}</>}
                      onConfirmar={(motivo) => anular(c, motivo)}
                      onCancelar={() => setPanel(null)}
                    />
                  )}
                </li>
              )
            })}
          </ul>
        )}

        <p className="subtitulo nota-precios">
          <span className="punto punto-verde" /> Pagado completo · <span className="punto punto-amarillo" /> Falta pagar una parte ·{' '}
          <span className="punto punto-rojo" /> Todavía no se pagó. La fecha y la hora las pone el sistema al anotar.
        </p>
      </main>
    </>
  )
}
