import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from './AuthContext'

// Solo deja pasar a usuarios con sesión iniciada.
// Si el usuario debe cambiar su contraseña (RF-14), lo manda a esa pantalla primero.
// Con `roles`, además exige uno de esos roles (RF-16); la API lo vuelve a verificar (RF-17).
export default function RutaProtegida({ children, roles }) {
  const { usuario, cargando } = useAuth()
  const { pathname } = useLocation()

  if (cargando) return <p className="cargando-pagina">Cargando…</p>
  if (!usuario) return <Navigate to="/login" replace />
  if (usuario.debe_cambiar_password && pathname !== '/cambiar-password') {
    return <Navigate to="/cambiar-password" replace />
  }
  if (roles && !roles.includes(usuario.rol)) return <Navigate to="/" replace />
  return children
}
