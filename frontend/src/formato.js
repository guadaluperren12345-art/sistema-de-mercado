// Formatos de Argentina para mostrar y cargar números.

const PESOS = new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS' })

// 6500.5 -> "$ 6.500,50"
export const pesos = (valor) => PESOS.format(Number(valor))

// Convierte lo que escribe la persona en un número para la API.
// Acepta "6500", "6500,50", "6.500,50" y "6500.50". Devuelve null si no es un número.
export function leerNumero(texto) {
  let t = String(texto).trim().replace(/\$|\s/g, '')
  if (!t) return null
  if (t.includes(',')) t = t.replace(/\./g, '').replace(',', '.') // formato argentino
  else if (/^\d{1,3}(\.\d{3})+$/.test(t)) t = t.replace(/\./g, '') // "6.500" = seis mil quinientos
  const n = Number(t)
  return Number.isFinite(n) ? n : null
}

// "c/u" o "/ kg" según cómo se vende el producto
export const porUnidad = (producto) => (producto.unidad === 'KG' ? '/ kg' : 'c/u')

// Margen de ganancia sobre el costo, en porcentaje. null si no se puede calcular.
export function margen(venta, costo) {
  if (venta == null || costo == null || costo <= 0) return null
  return ((venta - costo) / costo) * 100
}

// ---------- Cantidades de stock ----------

// 12.5 + "KG" -> "12,5 kg" · 24 + "UNIDAD" -> "24 u."
export function cantidad(valor, unidad) {
  const texto = Number(valor).toLocaleString('es-AR', { maximumFractionDigits: 3 })
  return unidad === 'KG' ? `${texto} kg` : `${texto} u.`
}

// Igual que cantidad(), pero con signo: "+12,5 kg" o "−3 u."
export function cantidadConSigno(valor, unidad) {
  const n = Number(valor)
  return `${n > 0 ? '+' : n < 0 ? '−' : ''}${cantidad(Math.abs(n), unidad)}`
}

// ---------- Fechas y horas ----------

const dos = (n) => String(n).padStart(2, '0')

// Date -> "2026-11-12" (en la hora local, no en UTC)
export const aFechaISO = (d) => `${d.getFullYear()}-${dos(d.getMonth() + 1)}-${dos(d.getDate())}`

// El día del mercado no termina a las 00:00 sino a las 00:45: a esa hora el sistema hace la caja.
// Si se cambia, cambiarla también en backend/core/dia.py (HORA_DE_CIERRE).
export const HORA_CIERRE = '00:45'
const MINUTOS_CIERRE = 45

// El día del mercado que está corriendo ahora (a las 00:20 del sábado todavía es viernes), sin hora
export function hoyDelMercado() {
  const d = new Date(Date.now() - MINUTOS_CIERRE * 60 * 1000)
  return new Date(d.getFullYear(), d.getMonth(), d.getDate())
}

// "2026-11-12" -> Date a las 00:00 de acá (new Date("2026-11-12") lo tomaría como UTC y daría el día anterior)
export function deFechaISO(texto) {
  const [a, m, d] = texto.split('-').map(Number)
  return new Date(a, m - 1, d)
}

// "14:05"
export const hora = (iso) =>
  new Date(iso).toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', hour12: false })

// "mar 10/11"
export function diaCorto(fecha) {
  const d = typeof fecha === 'string' && fecha.length === 10 ? deFechaISO(fecha) : new Date(fecha)
  const dia = d.toLocaleDateString('es-AR', { weekday: 'short' }).replace('.', '')
  return `${dia} ${dos(d.getDate())}/${dos(d.getMonth() + 1)}`
}

// "10/11/26 14:05"
export function fechaHora(iso) {
  const d = new Date(iso)
  return `${dos(d.getDate())}/${dos(d.getMonth() + 1)}/${String(d.getFullYear()).slice(2)} ${hora(iso)}`
}

// 455 minutos -> "7 h 35 min"
export function duracion(minutos) {
  const h = Math.floor(minutos / 60)
  const m = minutos % 60
  return h ? `${h} h ${dos(m)} min` : `${m} min`
}
