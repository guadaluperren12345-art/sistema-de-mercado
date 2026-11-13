import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth/AuthContext'
import Encabezado from '../componentes/Encabezado'
import FormularioStock from '../componentes/FormularioStock'
import ProductoNuevoRapido from '../componentes/ProductoNuevoRapido'
import { PRODUCTO_VACIO, unidadDe } from '../productoNuevo'
import { cantidad, leerNumero } from '../formato'
import { contenidoTexto, llegaEnBultos, nombrePresentacion, stockEnBultos } from '../presentaciones'

// Stock exacto de cada producto con semáforo (RF-34 a RF-38).
// Lo ven todos; solo dueños y encargados cargan mercadería, pérdidas y recuentos.

const COLORES = {
  ROJO: { clase: 'rojo', texto: 'Sin stock' },
  AMARILLO: { clase: 'amarillo', texto: 'Queda poco' },
  VERDE: { clase: 'verde', texto: 'Hay stock' },
}

const ORDEN = { ROJO: 0, AMARILLO: 1, VERDE: 2 }

export default function Stock() {
  const { usuario } = useAuth()
  const puedeMover = usuario.rol !== 'Empleado'
  const [secciones, setSecciones] = useState([])
  const [productos, setProductos] = useState([])
  const [seccion, setSeccion] = useState(null) // null = todas
  const [color, setColor] = useState(null) // null = todos
  // Cómo se muestra la cantidad: en unidades y kilos, o en cajas, cajones, bandejas… (RF-121)
  const [enBultos, setEnBultos] = useState(false)
  const [busqueda, setBusqueda] = useState('')
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')
  const [aviso, setAviso] = useState('')
  const [abierto, setAbierto] = useState(null) // { id, accion } del formulario que se está usando

  useEffect(() => {
    Promise.all([api('/api/secciones/'), api('/api/productos/?activo=1')])
      .then(([s, p]) => {
        setSecciones(s)
        setProductos(p)
      })
      .catch((err) => setError(err.message))
      .finally(() => setCargando(false))
  }, [])

  // Agregar al stock algo que todavía no existe: se crea el producto (queda también en Productos)
  // y enseguida se abre «Recibir mercadería» para cargar cuánto hay (RF-122)
  const [nuevo, setNuevo] = useState(null)
  const [erroresNuevo, setErroresNuevo] = useState({})
  const [creando, setCreando] = useState(false)

  const agregarCategoria = (c) =>
    setSecciones((lista) => lista.map((s) => (s.id === c.seccion ? { ...s, categorias: [...s.categorias, c] } : s)))

  const crearProducto = async (e) => {
    e.preventDefault()
    setError('')
    const venta = leerNumero(nuevo.venta)
    const costo = nuevo.costo.trim() ? leerNumero(nuevo.costo) : 0
    const errs = {}
    if (nuevo.nombre.trim().length < 2) errs.nombre = 'Escribí el nombre del producto.'
    if (!nuevo.seccionId) errs.seccion = 'Elegí la sección.'
    else if (!nuevo.categoria) errs.categoria = 'Elegí una categoría.'
    if (costo === null || costo < 0) errs.precio_costo = 'Escribí el costo con números.'
    if (venta === null || venta <= 0) errs.precio_venta = 'Escribí a cuánto se va a vender.'
    setErroresNuevo(errs)
    if (Object.keys(errs).length) return

    setCreando(true)
    try {
      const p = await api('/api/productos/', {
        metodo: 'POST',
        datos: {
          nombre: nuevo.nombre, categoria: Number(nuevo.categoria), unidad: unidadDe(nuevo, secciones),
          precio_costo: costo.toFixed(2), precio_venta: venta.toFixed(2),
        },
      })
      setProductos((lista) => [...lista, p])
      setNuevo(null)
      // Que quede a la vista, con el formulario para cargar cuánto hay
      setSeccion(null)
      setColor(null)
      setBusqueda('')
      setAbierto({ id: p.id, accion: 'ingreso' })
      setAviso(`«${p.nombre}» ya está cargado: aparece acá y en Productos. Ahora indicá cuánto hay para sumarlo al stock.`)
    } catch (err) {
      if (err.status === 400 && err.datos && !err.datos.detail) setErroresNuevo(err.datos)
      else setError(err.message)
    } finally {
      setCreando(false)
    }
  }

  const listo = (actualizado, mensaje) => {
    setProductos((lista) => lista.map((x) => (x.id === actualizado.id ? actualizado : x)))
    setAbierto(null)
    setAviso(mensaje)
  }

  const texto = busqueda.trim().toLowerCase()
  const deLaSeccion = productos.filter((p) => seccion === null || p.seccion_id === seccion)
  const cuenta = (c) => deLaSeccion.filter((p) => p.semaforo === c).length
  const visibles = deLaSeccion
    .filter((p) => color === null || p.semaforo === color)
    .filter((p) => (!texto || p.nombre.toLowerCase().includes(texto) || p.codigo === busqueda.trim() || p.codigo_barras === busqueda.trim()))
    .sort((a, b) => ORDEN[a.semaforo] - ORDEN[b.semaforo] || a.nombre.localeCompare(b.nombre))

  return (
    <>
      <Encabezado />
      <main className="contenedor">
        <div className="titulo-con-accion">
          <div>
            <h1>Stock</h1>
            <p className="subtitulo">Cuánto hay de cada producto. Primero aparece lo que falta.</p>
          </div>
          {puedeMover && (
            <div className="botones">
              <button onClick={() => { setNuevo(PRODUCTO_VACIO); setErroresNuevo({}); setAviso('') }}>+ Agregar un producto nuevo</button>
              <Link to="/stock/movimientos" className="boton boton-secundario">Ver movimientos</Link>
            </div>
          )}
        </div>

        {nuevo && (
          <form className="tarjeta panel-cuenta" onSubmit={crearProducto} noValidate>
            <strong>Agregar al stock un producto que todavía no existe</strong>
            <small className="texto-suave">
              Queda cargado también en Productos: es la misma lista. Después de guardarlo vas a poder indicar cuánto hay,
              por kilo, unidad, caja, cajón…
            </small>
            <ProductoNuevoRapido valor={nuevo} onCambiar={(v) => { setNuevo(v); setErroresNuevo({}) }} secciones={secciones}
              onNuevaCategoria={agregarCategoria} errores={erroresNuevo} pedirCosto />
            <div className="botones">
              <button type="submit" disabled={creando}>{creando ? 'Guardando…' : 'Guardar el producto'}</button>
              <button type="button" className="boton-secundario" onClick={() => setNuevo(null)}>Cancelar</button>
            </div>
          </form>
        )}

        <div className="chips" role="tablist" aria-label="Sección">
          <button role="tab" aria-selected={seccion === null} onClick={() => setSeccion(null)}>Todas</button>
          {secciones.map((s) => (
            <button key={s.id} role="tab" aria-selected={seccion === s.id} onClick={() => setSeccion(s.id)}>
              {s.nombre}
            </button>
          ))}
        </div>

        <div className="pestanas" role="tablist" aria-label="Estado del stock">
          <button role="tab" aria-selected={color === null} onClick={() => setColor(null)}>
            Todos ({deLaSeccion.length})
          </button>
          {Object.entries(COLORES).map(([clave, c]) => (
            <button key={clave} role="tab" aria-selected={color === clave} onClick={() => setColor(clave)}>
              <span className={`punto punto-${c.clase}`} /> {c.texto} ({cuenta(clave)})
            </button>
          ))}
        </div>

        <div className="chips" role="tablist" aria-label="Cómo ver las cantidades">
          <button role="tab" aria-selected={!enBultos} onClick={() => setEnBultos(false)}>Ver en unidades y kilos</button>
          <button role="tab" aria-selected={enBultos} onClick={() => setEnBultos(true)}>Ver en cajas, cajones, bandejas…</button>
        </div>

        <input type="search" className="buscador" placeholder="Buscar por nombre, número o código de barras (se puede escanear)"
          value={busqueda} onChange={(e) => setBusqueda(e.target.value)} />
        {enBultos && !visibles.some(llegaEnBultos) && visibles.length > 0 && (
          <p className="aviso">
            Ninguno de estos productos tiene anotado en qué llega. Se anota solo la primera vez que recibís o comprás
            mercadería eligiendo caja, cajón, bandeja, bolsa, pack o bulto.
          </p>
        )}

        {aviso && (
          <p className="mensaje-ok" role="status">
            {aviso} <button className="boton-texto" onClick={() => setAviso('')}>Cerrar</button>
          </p>
        )}
        {error && <p className="mensaje-error" role="alert">{error}</p>}

        {cargando ? (
          <p className="subtitulo">Cargando…</p>
        ) : visibles.length === 0 ? (
          <p className="subtitulo">
            {productos.length === 0
              ? 'Todavía no hay productos cargados.'
              : 'Ningún producto coincide con lo que elegiste.'}
          </p>
        ) : (
          <ul className="lista-usuarios">
            {visibles.map((p) => {
              const c = COLORES[p.semaforo]
              const accion = abierto?.id === p.id ? abierto.accion : null
              const abrir = (a) => { setAviso(''); setAbierto({ id: p.id, accion: a }) }
              return (
                <li key={p.id} className={`tarjeta fila-usuario borde-${c.clase}`}>
                  <div className="datos-usuario">
                    <strong>
                      {p.nombre}
                      {p.codigo && <span className="etiqueta">N° {p.codigo}</span>}
                    </strong>
                    <span className="texto-suave">
                      {p.seccion} → {p.categoria_nombre}
                      {llegaEnBultos(p) && <> · llega en {nombrePresentacion(p.presentacion)} de {contenidoTexto(p)}</>}
                    </span>
                  </div>

                  <div className="stock-cantidad">
                    <b className={`texto-${c.clase}`}>
                      <span className={`punto punto-${c.clase}`} />{' '}
                      {enBultos && stockEnBultos(p) ? stockEnBultos(p) : cantidad(p.stock_actual, p.unidad)}
                    </b>
                    <small className="texto-suave">
                      {c.texto}
                      {Number(p.stock_minimo) > 0 && <> · mínimo {cantidad(p.stock_minimo, p.unidad)}</>}
                      {stockEnBultos(p) && (enBultos
                        ? <> · son {cantidad(p.stock_actual, p.unidad)}</>
                        : <> · ≈ {stockEnBultos(p)}</>)}
                    </small>
                  </div>

                  {puedeMover && !accion && (
                    <div className="botones botones-stock">
                      <button className="boton-chico" onClick={() => abrir('ingreso')}>+ Recibir mercadería</button>
                      <button className="boton-chico boton-borde" onClick={() => abrir('perdida')}
                        disabled={Number(p.stock_actual) <= 0}
                        title={Number(p.stock_actual) <= 0 ? 'No hay stock para descontar' : undefined}>
                        Pérdida
                      </button>
                      <button className="boton-chico boton-borde" onClick={() => abrir('ajuste')}>Recuento</button>
                      <button className="boton-chico boton-borde" onClick={() => abrir('minimo')}>Mínimo</button>
                      <Link to={`/stock/movimientos?producto=${p.id}`} className="boton-enlace">Historial</Link>
                    </div>
                  )}

                  {accion && (
                    <FormularioStock key={accion} producto={p} accion={accion} onListo={listo}
                      onCancelar={() => setAbierto(null)} />
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </main>
    </>
  )
}
