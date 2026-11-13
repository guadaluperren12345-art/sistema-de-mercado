import { margen } from '../formato'
import { unidadDe } from '../productoNuevo'
import SelectorCategoria from './SelectorCategoria'

// Datos mínimos para crear un producto sin salir de la pantalla (RF-122). Se usa en Stock y en
// Compras a comerciantes: lo que se agrega ahí queda también en Productos, porque es la misma lista.
// `valor` = { nombre, seccionId, categoria, unidad, venta, costo } (ver productoNuevo.js).
// Con `costoConocido` (un número) no se pide el costo: sale de la compra.

export default function ProductoNuevoRapido({ valor, onCambiar, secciones, onNuevaCategoria, errores = {}, costoConocido, pedirCosto = false }) {
  const seccion = secciones.find((s) => s.id === valor.seccionId)
  const unidad = unidadDe(valor, secciones)
  const cambiar = (campo, v) => onCambiar({ ...valor, [campo]: v })
  const errorDe = (campo) => errores[campo] && <span className="error-campo">{[errores[campo]].flat().join(' ')}</span>

  const nVenta = Number(String(valor.venta).replace(/\./g, '').replace(',', '.'))
  const nCosto = costoConocido ?? Number(String(valor.costo).replace(/\./g, '').replace(',', '.'))
  const m = nVenta > 0 && nCosto > 0 ? margen(nVenta, nCosto) : null

  return (
    <div className="producto-nuevo">
      <label>
        Nombre del producto nuevo
        <input value={valor.nombre} maxLength={100} autoComplete="off" placeholder="Ej.: Cebolla"
          onChange={(e) => cambiar('nombre', e.target.value)} />
        {errorDe('nombre')}
      </label>

      <fieldset className="grupo">
        <legend>Sección</legend>
        <div className="opciones-fila">
          {secciones.map((s) => (
            <button type="button" key={s.id} className={`opcion-boton opcion-chica ${s.id === valor.seccionId ? 'elegida' : ''}`}
              aria-pressed={s.id === valor.seccionId}
              onClick={() => onCambiar({ ...valor, seccionId: s.id, categoria: '', unidad: null })}>
              {s.nombre}
            </button>
          ))}
        </div>
        {errorDe('seccion')}
      </fieldset>

      {seccion && (
        <SelectorCategoria
          seccion={seccion}
          valor={valor.categoria}
          onCambiar={(v) => cambiar('categoria', v)}
          onNueva={(c) => { onNuevaCategoria(c); cambiar('categoria', String(c.id)) }}
          error={errorDe('categoria')}
        />
      )}

      <fieldset className="grupo">
        <legend>Se vende</legend>
        <div className="opciones-fila">
          {[['UNIDAD', 'Por unidad'], ['KG', 'Por kilo']].map(([v, texto]) => (
            <button type="button" key={v} className={`opcion-boton opcion-chica ${unidad === v ? 'elegida' : ''}`}
              aria-pressed={unidad === v} onClick={() => cambiar('unidad', v)}>
              {texto}
            </button>
          ))}
        </div>
        {errorDe('unidad')}
      </fieldset>

      <div className="fila-precios">
        {pedirCosto && (
          <label>
            Costo <small>({unidad === 'KG' ? 'por kilo' : 'por unidad'})</small>
            <input value={valor.costo} inputMode="decimal" autoComplete="off" onChange={(e) => cambiar('costo', e.target.value)} />
            {errorDe('precio_costo')}
          </label>
        )}
        <label>
          Precio de venta <small>({unidad === 'KG' ? 'por kilo' : 'por unidad'})</small>
          <input value={valor.venta} inputMode="decimal" autoComplete="off" onChange={(e) => cambiar('venta', e.target.value)} />
          {m !== null && <small className={m < 0 ? 'texto-rojo' : 'texto-suave'}>{m < 0 ? 'Queda por debajo del costo' : `Margen ${m.toFixed(0)} %`}</small>}
          {errorDe('precio_venta')}
        </label>
      </div>
    </div>
  )
}
