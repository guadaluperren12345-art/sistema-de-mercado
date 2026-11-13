import { hoy, moverPeriodo, rangoDe, TIPOS_DE_PERIODO, tituloDePeriodo } from '../periodo'

// Elegir día, semana o mes y moverse hacia atrás o adelante. No deja ir al futuro.
export default function SelectorPeriodo({ tipo, ancla, onCambiar, tipos = TIPOS_DE_PERIODO }) {
  const siguiente = moverPeriodo(tipo, ancla, 1)
  const hayFuturo = rangoDe(tipo, siguiente).desde <= hoy()

  return (
    <div className="selector-periodo">
      <div className="chips" role="tablist" aria-label="Período">
        {tipos.map(([valor, texto]) => (
          <button key={valor} role="tab" aria-selected={tipo === valor} onClick={() => onCambiar(valor, hoy())}>
            {texto}
          </button>
        ))}
      </div>
      <div className="navegar-periodo">
        <button className="boton-chico boton-borde" aria-label="Anterior"
          onClick={() => onCambiar(tipo, moverPeriodo(tipo, ancla, -1))}>‹</button>
        <strong>{tituloDePeriodo(tipo, ancla)}</strong>
        <button className="boton-chico boton-borde" aria-label="Siguiente" disabled={!hayFuturo}
          onClick={() => onCambiar(tipo, siguiente)}>›</button>
      </div>
    </div>
  )
}
