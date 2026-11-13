import { useEffect, useState } from 'react'
import { api } from '../api'
import Encabezado from '../componentes/Encabezado'
import { leerNumero, margen, pesos, porUnidad } from '../formato'

// Módulo de precios (RF-90 a RF-94). Dueños y encargados.
// Se elige una sección y una categoría (ej.: Carnicería → Pollo) y se sube o baja un porcentaje
// a todos sus productos, o solo a los tildados. Antes de guardar se ve cómo queda cada precio.
// También se puede cambiar el precio de un solo producto con «Cambiar».

const APLICAR = [['VENTA', 'Precio de venta'], ['COSTO', 'Costo'], ['AMBOS', 'Los dos']]
const REDONDEOS = [[0, 'No redondear'], [1, 'Sin centavos'], [10, 'De a $ 10'], [50, 'De a $ 50'], [100, 'De a $ 100']]

const comoTexto = (n) => String(Math.round(n * 100) / 100)

export default function Precios() {
  const [secciones, setSecciones] = useState([])
  const [productos, setProductos] = useState([])
  const [cargando, setCargando] = useState(true)
  const [seccionId, setSeccionId] = useState(null)
  const [categoriaId, setCategoriaId] = useState(null)
  const [elegidos, setElegidos] = useState([]) // ids de los productos tildados
  const [sube, setSube] = useState(true)
  const [porcentaje, setPorcentaje] = useState('')
  const [aplicarA, setAplicarA] = useState('VENTA')
  const [redondeo, setRedondeo] = useState(0)
  const [previa, setPrevia] = useState(null) // { clave, filas: {id: fila}, error }
  const [confirmando, setConfirmando] = useState(false)
  const [enviando, setEnviando] = useState(false)
  const [editando, setEditando] = useState(null) // { id, venta, costo } del producto que se cambia a mano
  const [aviso, setAviso] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([api('/api/secciones/'), api('/api/productos/?activo=1')])
      .then(([s, p]) => {
        setSecciones(s)
        setProductos(p)
      })
      .catch((err) => setError(err.message))
      .finally(() => setCargando(false))
  }, [])

  const seccion = secciones.find((s) => s.id === seccionId)
  const categoria = seccion?.categorias.find((c) => c.id === categoriaId)
  const deLaCategoria = productos.filter((p) => p.categoria === categoriaId)
  const cuantos = (idCategoria) => productos.filter((p) => p.categoria === idCategoria).length

  const elegirSeccion = (id) => {
    setSeccionId(id)
    elegirCategoria(null)
  }

  const elegirCategoria = (id) => {
    setCategoriaId(id)
    setElegidos(productos.filter((p) => p.categoria === id).map((p) => p.id)) // arrancan todos tildados
    setConfirmando(false)
    setEditando(null)
    setAviso('')
    setError('')
  }

  const tildar = (id) => {
    setConfirmando(false)
    setElegidos((lista) => (lista.includes(id) ? lista.filter((x) => x !== id) : [...lista, id]))
  }

  // Lo que se le pide a la API. null mientras falte algo (categoría, porcentaje o productos).
  const n = leerNumero(porcentaje)
  const pedido =
    categoriaId && elegidos.length && n !== null && n > 0
      ? {
          categoria: categoriaId,
          productos: [...elegidos].sort((a, b) => a - b),
          porcentaje: comoTexto(sube ? n : -n),
          aplicar_a: aplicarA,
          redondeo,
        }
      : null
  const clave = pedido ? JSON.stringify(pedido) : ''

  // Vista previa: la calcula la API (sin guardar) un momento después de dejar de escribir
  useEffect(() => {
    if (!clave) return
    let vigente = true
    const espera = setTimeout(() => {
      api('/api/precios/ajuste/', { metodo: 'POST', datos: JSON.parse(clave) })
        .then((r) => vigente && setPrevia({ clave, filas: Object.fromEntries(r.productos.map((f) => [f.id, f])), error: '' }))
        .catch((err) => vigente && setPrevia({ clave, filas: {}, error: err.message }))
    }, 300)
    return () => {
      vigente = false
      clearTimeout(espera)
    }
  }, [clave])

  const previaActual = previa && previa.clave === clave ? previa : null
  const filas = previaActual?.filas ?? {}
  const cambian = Object.values(filas).filter((f) => f.cambia).length
  const bajoCosto = Object.values(filas).filter((f) => f.bajo_costo).length
  const signo = sube ? '+' : '−'
  const textoPorcentaje = n !== null ? `${signo}${comoTexto(n).replace('.', ',')} %` : ''

  const aplicar = async () => {
    setEnviando(true)
    setError('')
    try {
      const r = await api('/api/precios/ajuste/', { metodo: 'POST', datos: { ...pedido, confirmar: true } })
      setProductos(await api('/api/productos/?activo=1'))
      setAviso(
        `Listo: ${r.cambiados === 1 ? 'se cambió el precio de 1 producto' : `se cambiaron los precios de ${r.cambiados} productos`} de ${r.categoria.nombre} (${textoPorcentaje}).`,
      )
      setPorcentaje('')
      setPrevia(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setEnviando(false)
      setConfirmando(false)
    }
  }

  const guardarUno = async (e) => {
    e.preventDefault()
    const venta = leerNumero(editando.venta)
    const costo = leerNumero(editando.costo)
    if (venta === null || venta <= 0) return setError('El precio de venta tiene que ser mayor a 0.')
    if (costo === null || costo < 0) return setError('El costo no puede ser negativo.')
    setEnviando(true)
    setError('')
    try {
      const p = await api(`/api/productos/${editando.id}/precio/`, {
        metodo: 'POST',
        datos: { precio_venta: venta.toFixed(2), precio_costo: costo.toFixed(2) },
      })
      setProductos((lista) => lista.map((x) => (x.id === p.id ? p : x)))
      setAviso(`Listo: ${p.nombre} ahora sale ${pesos(p.precio_venta)}.`)
      setEditando(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setEnviando(false)
    }
  }

  const numero = (valor) => String(Number(valor)).replace('.', ',')

  return (
    <>
      <Encabezado />
      <main className="contenedor">
        <h1>Precios</h1>
        <p className="subtitulo">Subí o bajá un porcentaje a todos los productos de una categoría, o cambiá uno solo</p>

        {cargando && <p className="subtitulo">Cargando…</p>}

        <p className="etiqueta-campo">1. Elegí la sección</p>
        <div className="chips" role="tablist" aria-label="Sección">
          {secciones.map((s) => (
            <button key={s.id} role="tab" aria-selected={s.id === seccionId} onClick={() => elegirSeccion(s.id)}>
              {s.nombre}
            </button>
          ))}
        </div>

        {seccion && (
          <>
            <p className="etiqueta-campo">2. Elegí la categoría de {seccion.nombre}</p>
            {seccion.categorias.length === 0 ? (
              <p className="subtitulo">Esta sección todavía no tiene categorías. Se crean al dar de alta un producto.</p>
            ) : (
              <div className="chips" role="tablist" aria-label="Categoría">
                {seccion.categorias.map((c) => (
                  <button key={c.id} role="tab" aria-selected={c.id === categoriaId} onClick={() => elegirCategoria(c.id)}>
                    {c.nombre} ({cuantos(c.id)})
                  </button>
                ))}
              </div>
            )}
          </>
        )}

        {aviso && (
          <p className="mensaje-ok" role="status">
            {aviso} <button className="boton-texto" onClick={() => setAviso('')}>Cerrar</button>
          </p>
        )}
        {error && <p className="mensaje-error" role="alert">{error}</p>}

        {categoria && deLaCategoria.length === 0 && (
          <p className="subtitulo">No hay productos a la venta en {categoria.nombre}.</p>
        )}

        {categoria && deLaCategoria.length > 0 && (
          <>
            <div className="tarjeta panel-precios">
              <p className="etiqueta-campo">3. ¿Cuánto cambian los precios de {categoria.nombre}?</p>
              <div className="fila-precios">
                <div className="opciones-fila">
                  <button type="button" className={`opcion-boton ${sube ? 'elegida' : ''}`} aria-pressed={sube}
                    onClick={() => { setSube(true); setConfirmando(false) }}>
                    Subir
                  </button>
                  <button type="button" className={`opcion-boton ${!sube ? 'elegida' : ''}`} aria-pressed={!sube}
                    onClick={() => { setSube(false); setConfirmando(false) }}>
                    Bajar
                  </button>
                </div>
                <label>
                  Porcentaje (%)
                  <input value={porcentaje} inputMode="decimal" placeholder="Ej.: 20" maxLength={6} autoComplete="off"
                    onChange={(e) => { setPorcentaje(e.target.value); setConfirmando(false); setAviso('') }} />
                </label>
                <label>
                  Qué cambia
                  <select value={aplicarA} onChange={(e) => { setAplicarA(e.target.value); setConfirmando(false) }}>
                    {APLICAR.map(([valor, texto]) => <option key={valor} value={valor}>{texto}</option>)}
                  </select>
                </label>
                <label>
                  Redondear el precio de venta
                  <select value={redondeo} onChange={(e) => { setRedondeo(Number(e.target.value)); setConfirmando(false) }}>
                    {REDONDEOS.map(([valor, texto]) => <option key={valor} value={valor}>{texto}</option>)}
                  </select>
                </label>
              </div>

              {porcentaje.trim() !== '' && (n === null || n <= 0) && (
                <span className="error-campo">Escribí el porcentaje con números, sin el signo (ej.: 20).</span>
              )}
              {previaActual?.error && <span className="error-campo">{previaActual.error}</span>}
              {elegidos.length === 0 && <span className="error-campo">Tildá al menos un producto de la lista.</span>}
              {bajoCosto > 0 && (
                <p className="aviso">
                  Atención: {bajoCosto === 1 ? 'un producto queda' : `${bajoCosto} productos quedan`} con el precio de venta por debajo del costo.
                </p>
              )}

              {confirmando ? (
                <div className="confirmar-baja">
                  <span>
                    ¿{sube ? 'Subir' : 'Bajar'} un <b>{comoTexto(n).replace('.', ',')} %</b> {cambian === 1 ? 'el precio de' : 'los precios de'}{' '}
                    <b>{cambian} {cambian === 1 ? 'producto' : 'productos'}</b> de {categoria.nombre}? Las ventas ya hechas no cambian.
                  </span>
                  <div className="botones">
                    <button onClick={aplicar} disabled={enviando}>{enviando ? 'Guardando…' : 'Sí, cambiar los precios'}</button>
                    <button className="boton-secundario" onClick={() => setConfirmando(false)} disabled={enviando}>Cancelar</button>
                  </div>
                </div>
              ) : (
                <button disabled={!previaActual || previaActual.error || cambian === 0} onClick={() => { setError(''); setConfirmando(true) }}>
                  {previaActual && !previaActual.error && cambian > 0
                    ? `Aplicar ${textoPorcentaje} a ${cambian} ${cambian === 1 ? 'producto' : 'productos'}`
                    : 'Escribí el porcentaje para ver cómo quedan'}
                </button>
              )}
            </div>

            <div className="tabla-con-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Incluir</th>
                    <th>Producto</th>
                    <th className="numero">Costo</th>
                    <th className="numero">Precio de venta</th>
                    <th className="numero">Margen</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {deLaCategoria.map((p) => {
                    const f = filas[p.id]
                    const venta = f?.cambia ? f.precio_venta_nuevo : p.precio_venta
                    const costo = f?.cambia ? f.precio_costo_nuevo : p.precio_costo
                    const m = margen(Number(venta), Number(costo))
                    const cambiaVenta = f && Number(f.precio_venta_nuevo) !== Number(p.precio_venta)
                    const cambiaCosto = f && Number(f.precio_costo_nuevo) !== Number(p.precio_costo)
                    if (editando?.id === p.id) {
                      return (
                        <tr key={p.id}>
                          <td colSpan={6}>
                            <form className="editar-precio" onSubmit={guardarUno}>
                              <b>{p.nombre}</b>
                              <label>
                                Costo {porUnidad(p)}
                                <input value={editando.costo} inputMode="decimal" autoComplete="off"
                                  onChange={(e) => setEditando({ ...editando, costo: e.target.value })} />
                              </label>
                              <label>
                                Precio de venta {porUnidad(p)}
                                <input value={editando.venta} inputMode="decimal" autoComplete="off" autoFocus
                                  onChange={(e) => setEditando({ ...editando, venta: e.target.value })} />
                              </label>
                              <div className="botones">
                                <button type="submit" disabled={enviando}>{enviando ? 'Guardando…' : 'Guardar'}</button>
                                <button type="button" className="boton-secundario" onClick={() => { setEditando(null); setError('') }}>
                                  Cancelar
                                </button>
                              </div>
                            </form>
                          </td>
                        </tr>
                      )
                    }
                    return (
                      <tr key={p.id}>
                        <td>
                          <input type="checkbox" className="casilla" checked={elegidos.includes(p.id)}
                            onChange={() => tildar(p.id)} aria-label={`Incluir ${p.nombre}`} />
                        </td>
                        <td>
                          {p.nombre} <small className="texto-suave">{porUnidad(p)}</small>
                        </td>
                        <td className="numero">
                          {cambiaCosto && <span className="precio-viejo">{pesos(p.precio_costo)}</span>}
                          <span className={cambiaCosto ? 'precio-nuevo' : ''}>{pesos(costo)}</span>
                        </td>
                        <td className="numero">
                          {cambiaVenta && <span className="precio-viejo">{pesos(p.precio_venta)}</span>}
                          <b className={cambiaVenta ? 'precio-nuevo' : ''}>{pesos(venta)}</b>
                        </td>
                        <td className={`numero ${f?.bajo_costo ? 'texto-rojo' : ''}`}>{m === null ? '—' : `${m.toFixed(0)} %`}</td>
                        <td>
                          <button className="boton-texto"
                            onClick={() => { setError(''); setAviso(''); setConfirmando(false); setEditando({ id: p.id, venta: numero(p.precio_venta), costo: numero(p.precio_costo) }) }}>
                            Cambiar
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <p className="subtitulo nota-precios">
              Los precios tachados son los de ahora; en rosa, cómo quedan. No se guarda nada hasta que confirmes.
              Cada cambio queda registrado en la Actividad del sistema.
            </p>
          </>
        )}
      </main>
    </>
  )
}
