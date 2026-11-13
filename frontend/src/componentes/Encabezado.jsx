import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

// Barra superior con el usuario conectado y su rol (RF-04), presente en todas las pantallas.
export default function Encabezado() {
  const { usuario, logout } = useAuth()
  const { pathname } = useLocation()

  return (
    <header className="encabezado">
      <div>
        <strong>Sistema de Mercado</strong>
        <span className="usuario-conectado">
          {usuario.nombre_completo} · <span className={`rol rol-${usuario.rol.toLowerCase()}`}>{usuario.rol}</span>
        </span>
      </div>
      <nav>
        {pathname !== '/' && <Link to="/">Inicio</Link>}
        <Link to="/cambiar-password">Contraseña</Link>
        <button className="boton-chico" onClick={() => logout()}>Cerrar sesión</button>
      </nav>
    </header>
  )
}
