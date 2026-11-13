import { useState } from 'react'
import { api } from '../api'
import { cantidad, cantidadConSigno, leerNumero, pesos, porUnidad } from '../formato'
import { llegaEnBultos, nombrePresentacion, PRESENTACIONES } from '../presentaciones'

// Formulario que aparece debajo de un producto para mover su stock.
// accion: 'ingreso' (llegó mercadería), 'perdida', 'ajuste' (recuento) o 'minimo' (stock mínimo).
// La cantidad se carga por kilo o unidad, o por caja, cajón, bandeja, bolsa, pack o bulto (RF-121):
// «llegaron 3 cajones de 18 kg» y el sistema calcula los kilos o unidades.

const MOTIVOS = {
  perdida: ['Vencido', 'En mal estado', 'Rotura', 'Robo o faltante', 'Otro'],
  ajuste: ['Recuento de inventario', 'Carga inicial de stock', 'Error en una carga anterior', 'Otro'],
}

const TEXTOS = {
  ingreso: { titulo: 'Recibir mercadería', pregunta: '¿Cuánto llegó?', bultos: 'llegaron', boton: 'Sumar al stock' },
  perdida: { titulo: 'Registrar pérdida', pregunta: '¿Cuánto se perdió?', bultos: 'se perdieron', boton: 'Restar del stock' },
  ajuste: { titulo: 'Recuento', pregunta: '¿Cuánto hay en realidad?', bultos: 'hay en realidad', boton: 'Guardar recuento' },
  minimo: { titulo: 'Stock mínimo', pregunta: '¿Con cuánto hay que avisar que queda poco?', boton: 'Guardar mínimo' },
}

const aTexto = (n) => String(Number(n)).replace('.', ',')

export default function FormularioStock({ producto, accion, onListo, onCancelar }) {
  const eligePresentacion = accion !== 'minimo'
  const [valor, setValor] = useState(accion === 'minimo' ? aTexto(producto.stock_minimo) : '')
  // En qué se cuenta: SUELTO (kilos o unidades) o caja, cajón, bandeja… Al recibir se propone lo que el producto ya tiene cargado
  const [presentacion, setPresentacion] = useState(accion === 'ingreso' && llegaEnBultos(producto) ? producto.presentacion : 'SUELTO')
  const [contenido, setContenido] = useState(llegaEnBultos(producto) ? aTexto(producto.contenido) : '')
  const [costo, setCosto] = useState('')
  const [motivo, setMotivo] = useState(MOTIVOS[accion]?.[0] ?? '')
  const [detalle, setDetalle] = useState('')
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)

  const t = TEXTOS[accion]
  const unidad = producto.unidad === 'KG' ? 'kilos' : 'unidades'
  const actual = Number(producto.stock_actual)
  const numero = leerNumero(valor)
  const nContenido = leerNumero(contenido)
  const veCostos = 'precio_costo' in producto
  const porBulto = eligePresentacion && presentacion !== 'SUELTO'
  const bulto = nombrePresentacion(presentacion)
  const bultos = nombrePresentacion(presentacion, 2)

  // La cantidad en unidades o kilos (lo que de verdad se mueve en el stock)
  const total = porBulto
    ? (numero !== null && nContenido !== null ? Math.round(numero * nContenido * 1000) / 1000 : null)
    : numero
  // «¿Cuántas cajas…?» pero «¿Cuántos cajones…?»
  const cuantos = ['CAJA', 'BANDEJA', 'BOLSA'].includes(presentacion) ? 'Cuántas' : 'Cuántos'
  // Las cantidades por unidad ya terminan en punto («24 u.»): no se le agrega otro
  const frase = (texto) => (texto.endsWith('.') ? texto : `${texto}.`)
  const son = porBulto && total !== null ? `Son ${cantidad(total, producto.unidad)} en total. ` : ''

  // Cómo va a quedar el stock, para que la persona lo vea antes de confirmar
  let vistaPrevia = null
  if (total !== null && total >= 0) {
    if (accion === 'ingreso' && total > 0) vistaPrevia = son + frase(`Va a quedar en ${cantidad(actual + total, producto.unidad)}`)
    if (accion === 'perdida' && total > 0 && total <= actual) vistaPrevia = son + frase(`Va a quedar en ${cantidad(actual - total, producto.unidad)}`)
    if (accion === 'ajuste' && total !== actual) {
      vistaPrevia = son + frase(`El sistema tiene ${cantidad(actual, producto.unidad)}: se va a corregir ${cantidadConSigno(total - actual, producto.unidad)}`)
    }
  }

  const elegirPresentacion = (nueva) => {
    setPresentacion(nueva)
    // Si es la misma en la que llega el producto, ya se sabe cuánto trae cada una
    if (nueva !== 'SUELTO' && nueva === producto.presentacion && llegaEnBultos(producto)) setContenido(aTexto(producto.contenido))
    setValor('')
    setCosto('')
    setError('')
  }

  const enviar = async (e) => {
    e.preventDefault()
    setError('')
    if (numero === null) return setError('Escribí la cantidad con números.')
    if (porBulto && (nContenido === null || nContenido <= 0)) return setError(`Escribí cuánto trae cada ${bulto} (puede ser aproximado).`)
    const motivoCompleto = motivo === 'Otro' ? detalle.trim() : [motivo, detalle.trim()].filter(Boolean).join(': ')
    if (MOTIVOS[accion] && !motivoCompleto) return setError('Contá brevemente el motivo.')
    // Por caja, cajón…: cuántos, en qué y cuánto trae cada uno
    const enBultos = { bultos: String(numero), contenido: String(nContenido), presentacion }

    let ruta = `/api/productos/${producto.id}/${accion}/`
    let metodo = 'POST'
    let datos
    if (accion === 'ingreso') {
      datos = { motivo: detalle.trim(), ...(porBulto ? enBultos : { cantidad: String(numero) }) }
      if (costo.trim()) {
        const c = leerNumero(costo)
        if (c === null || c < 0) return setError('El costo no es un número válido.')
        datos[porBulto ? 'costo_bulto' : 'costo_unitario'] = String(c)
      }
    } else if (accion === 'perdida') {
      datos = { motivo: motivoCompleto, ...(porBulto ? enBultos : { cantidad: String(numero) }) }
    } else if (accion === 'ajuste') {
      datos = { motivo: motivoCompleto, ...(porBulto ? enBultos : { stock_real: String(numero) }) }
    } else {
      ruta = `/api/productos/${producto.id}/`
      metodo = 'PATCH'
      datos = { stock_minimo: String(numero) }
    }

    setEnviando(true)
    try {
      const actualizado = await api(ruta, { metodo, datos })
      const cuanto = porBulto
        ? `${aTexto(numero)} ${numero === 1 ? bulto : bultos} de ${producto.nombre} (${cantidad(total, producto.unidad)})`
        : `${cantidad(numero, producto.unidad)} de ${producto.nombre}`
      const mensajes = {
        ingreso: `Se sumaron ${cuanto}.`,
        perdida: `Se registró la pérdida de ${cuanto}.`,
        ajuste: `El stock de ${producto.nombre} quedó en ${cantidad(total, producto.unidad)}${porBulto ? ` (${aTexto(numero)} ${numero === 1 ? bulto : bultos})` : ''}.`,
        minimo: `El stock mínimo de ${producto.nombre} quedó en ${cantidad(numero, producto.unidad)}.`,
      }
      onListo(actualizado, mensajes[accion])
    } catch (err) {
      setError(err.message)
      setEnviando(false)
    }
  }

  return (
    <form className={`panel-stock ${accion === 'perdida' ? 'panel-rojo' : ''}`} onSubmit={enviar} noValidate>
      <strong>{t.titulo} · {producto.nombre}</strong>

      {eligePresentacion && (
        <fieldset className="grupo">
          <legend>¿En qué lo contás?</legend>
          <div className="opciones-fila">
            {PRESENTACIONES.map(([valorP, nombre]) => (
              <button type="button" key={valorP} aria-pressed={presentacion === valorP}
                className={`opcion-boton opcion-chica ${presentacion === valorP ? 'elegida' : ''}`}
                onClick={() => elegirPresentacion(valorP)}>
                {valorP === 'SUELTO' ? (producto.unidad === 'KG' ? 'Por kilo' : 'Por unidad') : nombre}
              </button>
            ))}
          </div>
        </fieldset>
      )}

      <label>
        {porBulto ? `¿${cuantos} ${bultos} ${t.bultos}?` : t.pregunta}{' '}
        {!porBulto && <small>(en {unidad})</small>}
        <input value={valor} inputMode="decimal" autoFocus autoComplete="off"
          placeholder={porBulto ? 'Ej.: 3' : producto.unidad === 'KG' ? 'Ej.: 12,5' : 'Ej.: 24'}
          onChange={(e) => { setValor(e.target.value); setError('') }} />
      </label>

      {porBulto && (
        <label>
          Cada {bulto} trae <small>(en {unidad}; puede ser aproximado)</small>
          <input value={contenido} inputMode="decimal" autoComplete="off" placeholder={producto.unidad === 'KG' ? 'Ej.: 18' : 'Ej.: 12'}
            onChange={(e) => { setContenido(e.target.value); setError('') }} />
        </label>
      )}

      {accion === 'ingreso' && veCostos && (
        <label>
          {porBulto ? `Costo de cada ${bulto}` : `Costo ${porUnidad(producto)}`}{' '}
          <small>(opcional: si vino a otro precio que {pesos(producto.precio_costo)} {porUnidad(producto)})</small>
          <input value={costo} inputMode="decimal" autoComplete="off"
            placeholder={porBulto && nContenido ? aTexto(Number(producto.precio_costo) * nContenido) : aTexto(producto.precio_costo)}
            onChange={(e) => { setCosto(e.target.value); setError('') }} />
        </label>
      )}

      {MOTIVOS[accion] && (
        <label>
          Motivo
          <select value={motivo} onChange={(e) => setMotivo(e.target.value)}>
            {MOTIVOS[accion].map((m) => <option key={m}>{m}</option>)}
          </select>
        </label>
      )}

      {accion !== 'minimo' && (
        <label>
          {accion === 'ingreso' ? 'Nota' : 'Detalle'}{' '}
          <small>{motivo === 'Otro' ? '(contá qué pasó)' : accion === 'ingreso' ? '(opcional: comerciante, remito…)' : '(opcional)'}</small>
          <input value={detalle} maxLength={150} onChange={(e) => { setDetalle(e.target.value); setError('') }} />
        </label>
      )}

      {accion === 'minimo' && (
        <small className="texto-suave">
          Cuando el stock llegue a esa cantidad o menos, el producto pasa a amarillo. Con 0 no avisa hasta quedarse sin nada.
        </small>
      )}
      {accion === 'ingreso' && porBulto && !llegaEnBultos(producto) && (
        <small className="texto-suave">
          Este producto queda anotado como que llega en {bulto}: después el stock también se va a poder ver en {bultos}.
        </small>
      )}
      {vistaPrevia && <small className="texto-suave">{vistaPrevia}</small>}
      {error && <p className="mensaje-error" role="alert">{error}</p>}

      <div className="botones">
        <button type="submit" className={accion === 'perdida' ? 'boton-peligro' : ''} disabled={enviando}>
          {enviando ? 'Guardando…' : t.boton}
        </button>
        <button type="button" className="boton-secundario" onClick={onCancelar}>Cancelar</button>
      </div>
    </form>
  )
}
