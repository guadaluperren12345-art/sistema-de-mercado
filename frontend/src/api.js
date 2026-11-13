// Cliente para hablar con la API de Django.
// Guarda los tokens JWT y los renueva automáticamente cuando vencen.

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

const CLAVE_ACCESS = 'mercado.access'
const CLAVE_REFRESH = 'mercado.refresh'

// Evento que se dispara cuando la API rechaza la sesión. Lo escucha AuthContext.
export const EVENTO_SESION_TERMINADA = 'mercado:sesion-terminada'

function leer(clave) {
  try {
    return localStorage.getItem(clave)
  } catch {
    return null
  }
}

export function guardarTokens({ access, refresh }) {
  try {
    if (access) localStorage.setItem(CLAVE_ACCESS, access)
    if (refresh) localStorage.setItem(CLAVE_REFRESH, refresh)
  } catch {
    /* almacenamiento no disponible: la sesión dura hasta recargar */
  }
}

export function borrarTokens() {
  try {
    localStorage.removeItem(CLAVE_ACCESS)
    localStorage.removeItem(CLAVE_REFRESH)
  } catch {
    /* nada que borrar */
  }
}

export const hayTokens = () => Boolean(leer(CLAVE_REFRESH))
export const tokenRefresh = () => leer(CLAVE_REFRESH)

// Error con el mensaje que devuelve la API, listo para mostrar en pantalla
export class ErrorApi extends Error {
  constructor(status, datos) {
    super(mensajeDeError(datos))
    this.status = status
    this.datos = datos
  }
}

function mensajeDeError(datos) {
  if (!datos) return 'No se pudo conectar con el servidor.'
  if (typeof datos.detail === 'string') return datos.detail
  // Errores de validación: { campo: ["mensaje", ...] }
  const primero = Object.values(datos).flat()[0]
  return typeof primero === 'string' ? primero : 'Ocurrió un error inesperado.'
}

let renovando = null // evita pedir dos renovaciones a la vez

async function renovarToken() {
  const refresh = leer(CLAVE_REFRESH)
  if (!refresh) return false
  renovando ??= fetch(`${API_URL}/api/auth/refresh/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh }),
  })
    .then(async (res) => {
      if (!res.ok) return false
      guardarTokens(await res.json())
      return true
    })
    .catch(() => false)
    .finally(() => {
      renovando = null
    })
  return renovando
}

// Hace una petición a la API. Si el token venció, lo renueva y reintenta una vez.
export async function api(ruta, { metodo = 'GET', datos, autenticado = true } = {}, reintento = true) {
  const headers = { 'Content-Type': 'application/json' }
  const access = leer(CLAVE_ACCESS)
  if (autenticado && access) headers.Authorization = `Bearer ${access}`

  let res
  try {
    res = await fetch(`${API_URL}${ruta}`, {
      method: metodo,
      headers,
      body: datos ? JSON.stringify(datos) : undefined,
    })
  } catch {
    throw new ErrorApi(0, null)
  }

  if (res.status === 401 && autenticado && reintento && (await renovarToken())) {
    return api(ruta, { metodo, datos, autenticado }, false)
  }

  const cuerpo = res.status === 204 ? null : await res.json().catch(() => null)
  if (res.status === 401 && autenticado) {
    // La sesión ya no sirve (venció, o el turno terminó a las 00:00): se avisa para volver al login
    // Con `code` es el aviso técnico de token vencido; sin él es un mensaje nuestro ("Tu turno terminó…")
    const detalle = cuerpo?.code ? '' : mensajeDeError(cuerpo)
    window.dispatchEvent(new CustomEvent(EVENTO_SESION_TERMINADA, { detail: detalle }))
  }
  if (!res.ok) throw new ErrorApi(res.status, cuerpo)
  return cuerpo
}
