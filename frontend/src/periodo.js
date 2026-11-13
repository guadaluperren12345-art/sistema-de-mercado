// Períodos para los reportes: un día, una semana (lunes a domingo) o un mes.

import { aFechaISO } from './formato'

export const TIPOS_DE_PERIODO = [['dia', 'Día'], ['semana', 'Semana'], ['mes', 'Mes']]

const sinHora = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate())

export const hoy = () => sinHora(new Date())

// Primer y último día del período que contiene a `ancla`
export function rangoDe(tipo, ancla) {
  const d = sinHora(ancla)
  if (tipo === 'semana') {
    const lunes = new Date(d)
    lunes.setDate(d.getDate() - ((d.getDay() + 6) % 7))
    const domingo = new Date(lunes)
    domingo.setDate(lunes.getDate() + 6)
    return { desde: lunes, hasta: domingo }
  }
  if (tipo === 'mes') {
    return { desde: new Date(d.getFullYear(), d.getMonth(), 1), hasta: new Date(d.getFullYear(), d.getMonth() + 1, 0) }
  }
  if (tipo === 'anio') {
    return { desde: new Date(d.getFullYear(), 0, 1), hasta: new Date(d.getFullYear(), 11, 31) }
  }
  return { desde: d, hasta: d }
}

// El período anterior (-1) o el siguiente (+1)
export function moverPeriodo(tipo, ancla, pasos) {
  const d = sinHora(ancla)
  if (tipo === 'mes') return new Date(d.getFullYear(), d.getMonth() + pasos, 1)
  if (tipo === 'anio') return new Date(d.getFullYear() + pasos, 0, 1)
  d.setDate(d.getDate() + pasos * (tipo === 'semana' ? 7 : 1))
  return d
}

const corta = (d) => d.toLocaleDateString('es-AR', { day: 'numeric', month: 'short' })

export function tituloDePeriodo(tipo, ancla) {
  const { desde, hasta } = rangoDe(tipo, ancla)
  if (tipo === 'mes') {
    const t = desde.toLocaleDateString('es-AR', { month: 'long', year: 'numeric' })
    return t[0].toUpperCase() + t.slice(1)
  }
  if (tipo === 'anio') return `Año ${desde.getFullYear()}`
  if (tipo === 'semana') return `${corta(desde)} al ${corta(hasta)}`
  if (aFechaISO(desde) === aFechaISO(hoy())) return 'Hoy'
  const t = desde.toLocaleDateString('es-AR', { weekday: 'long', day: 'numeric', month: 'long' })
  return t[0].toUpperCase() + t.slice(1)
}

// Parámetros ?desde=&hasta= para la API
export function parametrosDe(tipo, ancla) {
  const { desde, hasta } = rangoDe(tipo, ancla)
  return `desde=${aFechaISO(desde)}&hasta=${aFechaISO(hasta)}`
}
