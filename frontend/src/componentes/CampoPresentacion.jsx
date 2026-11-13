import { nombrePresentacion, PRESENTACIONES } from '../presentaciones'

// Para el alta y la edición de productos: en qué llega (suelto, caja, cajón, bandeja…)
// y cuántas unidades o kilos trae cada una.
export default function CampoPresentacion({ presentacion, contenido, unidad, onPresentacion, onContenido, error }) {
  const nombre = nombrePresentacion(presentacion)
  return (
    <>
      <fieldset className="grupo">
        <legend>¿Cómo llega del comerciante?</legend>
        <div className="opciones-fila">
          {PRESENTACIONES.map(([valor, texto]) => (
            <button type="button" key={valor} className={`opcion-boton opcion-chica ${presentacion === valor ? 'elegida' : ''}`}
              aria-pressed={presentacion === valor} onClick={() => onPresentacion(valor)}>
              {texto}
            </button>
          ))}
        </div>
      </fieldset>

      {presentacion !== 'SUELTO' && (
        <label>
          ¿Cuánto trae cada {nombre}? <small>(en {unidad === 'KG' ? 'kilos' : 'unidades'})</small>
          <input value={contenido} inputMode="decimal" autoComplete="off"
            placeholder={unidad === 'KG' ? 'Ej.: 18' : 'Ej.: 12'}
            onChange={(e) => onContenido(e.target.value)} />
          <small className="texto-suave">
            Se sigue vendiendo {unidad === 'KG' ? 'por kilo' : 'por unidad'}. Esto sirve para cargar rápido lo que llega:
            se escribe cuántos {nombrePresentacion(presentacion, 2)} llegaron y el sistema calcula el total.
          </small>
          {error}
        </label>
      )}
    </>
  )
}
