import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { api } from '../api'
import ConfirmarBaja from '../componentes/ConfirmarBaja'
import Encabezado from '../componentes/Encabezado'
import { cantidad, margen, pesos, porUnidad } from '../formato'
import { stockEnBultos } from '../presentaciones'

// Lista de productos por sección, con altas, bajas y reactivaciones (RF-31, RF-33, RF-38).
// Dueños y encargados.

const SEMAFORO = { ROJO: 'rojo', AMARILLO: 'amarillo', VERDE: 'verde' }

export default function Productos() {
  const [secciones, setSecciones] = useState([])
  const [productos, setProductos] = useState([])
  const [seccion, setSeccion] = useState(null) // null = todas
  const [verActivos, setVerActivos] = useState(true)
  const [busqueda, setBusqueda] = useState('')
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')
  // Mensaje que deja la pantalla de edición al volver ("Se guardaron los cambios…")
  const [aviso, setAviso] = useState(useLocation().state?.aviso ?? '')
  const [dandoDeBaja, setDandoDeBaja] = useState(null)

  useEffect(() => {
    Promise.all([api('/api/secciones/'), api('/api/productos/')])
      .then(([s, p]) => {
        setSecciones(s)
        setProductos(p)
      })
      .catch((err) => setError(err.message))
      .finally(() => setCargando(false))
  }, [])

  const actualizar = (p) => setProductos((lista) => lista.map((x) => (x.id === p.id ? p : x)))

  const accion = async (p, ruta, datos, mensaje) => {
    setError('')
    try {
      actualizar(await api(`/api/productos/${p.id}/${ruta}/`, { metodo: 'POST', datos }))
      setDandoDeBaja(null)
      setAviso(mensaje)
    } catch (err) {
      setError(err.message)
    }
  }

  const texto = busqueda.trim().toLowerCase()
  const deLaSeccion = productos.filter((p) => seccion === null || p.seccion_id === seccion)
  const visibles = deLaSeccion.filter(
    (p) =>
      p.activo === verActivos &&
      (!texto || p.nombre.toLowerCase().includes(texto) || p.codigo === busqueda.trim() || p.codigo_barras === busqueda.trim()),
  )
  const cantidadActivos = deLaSeccion.filter((p) => p.activo).length

  return (
    <>
      <Encabezado />
      <main className="contenedor">
        <div className="titulo-con-accion">
          <div>
            <h1>Productos</h1>
            <p className="subtitulo">Lo que se vende en cada sección del mercado. Es la misma lista que se ve en Stock.</p>
          </div>
          <Link to={`/productos/nuevo${seccion ? `?seccion=${seccion}` : ''}`} className="boton">
            + Nuevo producto
          </Link>
        </div>

        <div className="chips" role="tablist" aria-label="Sección">
          <button role="tab" aria-selected={seccion === null} onClick={() => setSeccion(null)}>Todas</button>
          {secciones.map((s) => (
            <button key={s.id} role="tab" aria-selected={seccion === s.id} onClick={() => setSeccion(s.id)}>
              {s.nombre}
            </button>
          ))}
        </div>

        <div className="pestanas" role="tablist">
          <button role="tab" aria-selected={verActivos} onClick={() => setVerActivos(true)}>
            A la venta ({cantidadActivos})
          </button>
          <button role="tab" aria-selected={!verActivos} onClick={() => setVerActivos(false)}>
            Dados de baja ({deLaSeccion.length - cantidadActivos})
          </button>
        </div>

        <input
          type="search"
          className="buscador"
          placeholder="Buscar por nombre, número o código de barras (se puede escanear)"
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
        />

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
            {texto
              ? 'Ningún producto coincide con la búsqueda.'
              : verActivos
                ? 'Todavía no hay productos cargados acá. Usá "+ Nuevo producto".'
                : 'No hay productos dados de baja.'}
          </p>
        ) : (
          <ul className="lista-usuarios">
            {visibles.map((p) => {
              const m = margen(Number(p.precio_venta), Number(p.precio_costo))
              return (
                <li key={p.id} className="tarjeta fila-usuario">
                  <div className="datos-usuario">
                    <strong>
                      {p.nombre}
                      {p.codigo && <span className="etiqueta">N° {p.codigo}</span>}
                      {p.codigo_barras && <span className="etiqueta">Barras {p.codigo_barras}</span>}
                    </strong>
                    <span className="texto-suave">
                      {p.seccion} → {p.categoria_nombre}
                      {p.presentacion !== 'SUELTO' && <> · llega en {p.presentacion_texto.toLowerCase()}</>}
                    </span>
                    <span>
                      <b className="precio">{pesos(p.precio_venta)}</b> {porUnidad(p)}
                      {'precio_costo' in p && (
                        <small className="texto-suave">
                          {' '}· costo {pesos(p.precio_costo)}
                          {m !== null && <> · margen {m.toFixed(0)}%</>}
                        </small>
                      )}
                    </span>
                    {/* El mismo stock que en la pantalla Stock, con su color */}
                    <span className={`stock-en-productos texto-${SEMAFORO[p.semaforo]}`}>
                      <span className={`punto punto-${SEMAFORO[p.semaforo]}`} /> Stock: {cantidad(p.stock_actual, p.unidad)}
                      {stockEnBultos(p) && <small className="texto-suave"> · ≈ {stockEnBultos(p)}</small>}
                    </span>
                  </div>

                  {dandoDeBaja === p.id ? (
                    <ConfirmarBaja
                      mensaje={<>¿Dar de baja <b>{p.nombre}</b>? Deja de aparecer para vender, pero sus ventas anteriores se conservan. Se puede reactivar.</>}
                      onConfirmar={(motivo) => accion(p, 'desactivar', { motivo }, `${p.nombre} fue dado de baja.`)}
                      onCancelar={() => setDandoDeBaja(null)}
                    />
                  ) : (
                    <div className="botones">
                      <Link to={`/productos/${p.id}/editar`} className="boton boton-secundario">Editar</Link>
                      {p.activo && <Link to="/stock" className="boton boton-secundario">Ver en Stock</Link>}
                      {p.activo ? (
                        <button className="boton-peligro" onClick={() => { setAviso(''); setDandoDeBaja(p.id) }}>
                          Dar de baja
                        </button>
                      ) : (
                        <button className="boton-secundario"
                          onClick={() => accion(p, 'reactivar', undefined, `${p.nombre} volvió a estar a la venta.`)}>
                          Reactivar
                        </button>
                      )}
                    </div>
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
