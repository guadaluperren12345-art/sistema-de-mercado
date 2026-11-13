import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import Encabezado from '../componentes/Encabezado'
import { cantidad, cantidadConSigno, fechaHora, pesos } from '../formato'
import { useConsulta } from '../useConsulta'

// Historial de entradas y salidas de mercadería (RF-35). Dueños y encargados.
// Con ?producto=ID muestra solo los movimientos de ese producto.

const TIPOS = [
  [null, 'Todos'],
  ['INGRESO', 'Ingresos'],
  ['PERDIDA', 'Pérdidas'],
  ['AJUSTE', 'Recuentos'],
]

export default function MovimientosStock() {
  const [params] = useSearchParams()
  const productoId = params.get('producto')
  const [tipo, setTipo] = useState(null)
  const [desde, setDesde] = useState('')
  const [hasta, setHasta] = useState('')

  const q = new URLSearchParams()
  if (productoId) q.set('producto', productoId)
  if (tipo) q.set('tipo', tipo)
  if (desde) q.set('desde', desde)
  if (hasta) q.set('hasta', hasta)
  const { datos: movimientos, error } = useConsulta(`/api/movimientos/?${q}`) // null = cargando
  const { datos: producto } = useConsulta(productoId ? `/api/productos/${productoId}/` : null)

  return (
    <>
      <Encabezado />
      <main className="contenedor">
        <div className="titulo-con-accion">
          <div>
            <h1>Movimientos de stock</h1>
            <p className="subtitulo">
              {producto
                ? <>De <b>{producto.nombre}</b> · hoy hay {cantidad(producto.stock_actual, producto.unidad)} · <Link to="/stock/movimientos">ver todos los productos</Link></>
                : 'Todo lo que entró y salió, con quién lo cargó y cuándo'}
            </p>
          </div>
          <Link to="/stock" className="boton boton-secundario">Volver al stock</Link>
        </div>

        <div className="chips" role="tablist" aria-label="Tipo de movimiento">
          {TIPOS.map(([valor, texto]) => (
            <button key={texto} role="tab" aria-selected={tipo === valor} onClick={() => setTipo(valor)}>{texto}</button>
          ))}
        </div>

        <div className="filtros">
          <label>Desde <input type="date" value={desde} max={hasta || undefined} onChange={(e) => setDesde(e.target.value)} /></label>
          <label>Hasta <input type="date" value={hasta} min={desde || undefined} onChange={(e) => setHasta(e.target.value)} /></label>
          {(desde || hasta) && (
            <button className="boton-texto" onClick={() => { setDesde(''); setHasta('') }}>Quitar fechas</button>
          )}
        </div>

        {error && <p className="mensaje-error" role="alert">{error}</p>}

        {error ? null : movimientos === null ? (
          <p className="subtitulo">Cargando…</p>
        ) : movimientos.length === 0 ? (
          <p className="subtitulo">No hay movimientos con esos filtros.</p>
        ) : (
          <>
            <ul className="lista-usuarios">
              {movimientos.map((m) => (
                <li key={m.id} className="tarjeta fila-usuario">
                  <div className="datos-usuario">
                    <strong>
                      <span className={`etiqueta etiqueta-${m.tipo.toLowerCase()} sin-margen`}>{m.tipo_texto}</span>{' '}
                      {m.producto_nombre}
                    </strong>
                    <span className="texto-suave">
                      {fechaHora(m.fecha_hora)} · {m.usuario} · {m.seccion}
                    </span>
                    {m.motivo && <span>{m.motivo}</span>}
                  </div>
                  <div className="stock-cantidad">
                    <b className={Number(m.cantidad) < 0 ? 'texto-rojo' : 'texto-verde'}>
                      {cantidadConSigno(m.cantidad, m.unidad)}
                    </b>
                    <small className="texto-suave">
                      quedó en {cantidad(m.stock_resultante, m.unidad)} · {pesos(Math.abs(Number(m.valor)))} al costo
                    </small>
                  </div>
                </li>
              ))}
            </ul>
            {movimientos.length >= 300 && (
              <p className="subtitulo">Se muestran los últimos 300. Usá las fechas para ver movimientos más viejos.</p>
            )}
          </>
        )}
      </main>
    </>
  )
}
