import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, borrarTokens, EVENTO_SESION_TERMINADA, guardarTokens, hayTokens, tokenRefresh } from '../api'

const AuthContext = createContext(null)

const MINUTOS_INACTIVIDAD = 30 // RF-06

export function AuthProvider({ children }) {
  const [usuario, setUsuario] = useState(null)
  const [cargando, setCargando] = useState(hayTokens())
  // Mensaje para la pantalla de login cuando la sesión se cerró sola ("Tu turno terminó…")
  const [avisoSesion, setAvisoSesion] = useState('')

  // Al abrir la página, si había una sesión guardada, recupera los datos del usuario
  useEffect(() => {
    if (!hayTokens()) return
    api('/api/auth/yo/')
      .then(setUsuario)
      .catch(() => borrarTokens())
      .finally(() => setCargando(false))
  }, [])

  const login = useCallback(async (nombre_usuario, password) => {
    const datos = await api('/api/auth/login/', {
      metodo: 'POST',
      datos: { nombre_usuario, password },
      autenticado: false,
    })
    guardarTokens(datos)
    setAvisoSesion('')
    setUsuario(datos.usuario)
    return datos.usuario
  }, [])

  // Cerrar sesión termina el turno: hasta acá se cuenta el horario de trabajo (RF-23).
  // `motivo` es 'inactividad' cuando la cierra el temporizador de abajo.
  const logout = useCallback(async (motivo) => {
    const refresh = tokenRefresh()
    const porInactividad = motivo === 'inactividad'
    if (refresh) {
      // La API identifica a la persona por este token, aunque el de acceso ya haya vencido
      const datos = porInactividad ? { refresh, motivo } : { refresh }
      await api('/api/auth/logout/', { metodo: 'POST', datos, autenticado: false }).catch(() => {})
    }
    borrarTokens()
    setAvisoSesion(porInactividad ? 'La sesión se cerró porque pasaron 30 minutos sin usar el sistema.' : '')
    setUsuario(null)
  }, [])

  const cambiarPassword = useCallback(async (password_actual, password_nueva) => {
    const datos = await api('/api/auth/cambiar-password/', {
      metodo: 'POST',
      datos: { password_actual, password_nueva },
    })
    setUsuario(datos)
  }, [])

  // La API rechazó la sesión (venció, o el turno se cerró): vuelve al login
  useEffect(() => {
    const terminar = (e) => {
      borrarTokens()
      setAvisoSesion(e.detail || 'La sesión venció. Volvé a ingresar.')
      setUsuario(null)
    }
    window.addEventListener(EVENTO_SESION_TERMINADA, terminar)
    return () => window.removeEventListener(EVENTO_SESION_TERMINADA, terminar)
  }, [])

  // Cierre automático de sesión por inactividad (RF-06)
  useEffect(() => {
    if (!usuario) return
    let temporizador
    const reiniciar = () => {
      clearTimeout(temporizador)
      temporizador = setTimeout(() => logout('inactividad'), MINUTOS_INACTIVIDAD * 60 * 1000)
    }
    const eventos = ['mousemove', 'keydown', 'click', 'touchstart', 'scroll']
    eventos.forEach((e) => window.addEventListener(e, reiniciar, { passive: true }))
    reiniciar()
    return () => {
      clearTimeout(temporizador)
      eventos.forEach((e) => window.removeEventListener(e, reiniciar))
    }
  }, [usuario, logout])

  return (
    <AuthContext.Provider value={{ usuario, cargando, avisoSesion, login, logout, cambiarPassword }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
