// En qué llega la mercadería del comerciante: suelta, o en caja, cajón, bandeja, bolsa, pack o bulto.
// El stock y la venta siguen siendo por unidad o por kilo; la presentación sirve para cargar
// más rápido lo que llega: «3 cajones de 18 kg» = 54 kg.

import { cantidad } from './formato'

// [valor para la API, nombre, plural]
export const PRESENTACIONES = [
  ['SUELTO', 'Suelto', 'sueltos'],
  ['CAJA', 'Caja', 'cajas'],
  ['CAJON', 'Cajón', 'cajones'],
  ['BANDEJA', 'Bandeja', 'bandejas'],
  ['BOLSA', 'Bolsa', 'bolsas'],
  ['PACK', 'Pack', 'packs'],
  ['BULTO', 'Bulto', 'bultos'],
]

const buscar = (valor) => PRESENTACIONES.find(([v]) => v === valor) ?? PRESENTACIONES[0]

// "cajón" o "cajones", en minúscula
export const nombrePresentacion = (valor, cuantos = 1) =>
  cuantos === 1 ? buscar(valor)[1].toLowerCase() : buscar(valor)[2]

export const llegaEnBultos = (producto) => producto.presentacion !== 'SUELTO' && Number(producto.contenido) > 0

// Stock expresado en cajas o cajones: "3 cajones", "2,5 cajas". null si el producto llega suelto o no hay stock.
export function stockEnBultos(producto) {
  if (!llegaEnBultos(producto)) return null
  const bultos = Number(producto.stock_actual) / Number(producto.contenido)
  if (bultos <= 0) return null
  const redondeado = Math.round(bultos * 10) / 10
  return `${redondeado.toLocaleString('es-AR')} ${nombrePresentacion(producto.presentacion, redondeado)}`
}

// "18 kg" o "6 u." que trae cada bulto
export const contenidoTexto = (producto) => cantidad(producto.contenido, producto.unidad)
