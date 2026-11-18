import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { api } from '../api'
import { EVENTO_AVISOS } from '../avisos'
import { useAuth } from '../auth/AuthContext'

const SEGUNDOS_ENTRE_REVISIONES = 60

// Cuántos avisos sin leer tiene el dueño. Se revisa cada minuto; si llega uno nuevo y el navegador
// tiene permiso, muestra además una notificación de la computadora (solo funciona en la PC del mercado).
function useAvisosSinLeer(activo) {
  const [sinLeer, setSinLeer] = useState(0)
  const anterior = useRef(null)

  useEffect(() => {
    if (!activo) return
    let vigente = true
    const revisar = () =>
      api('/api/notificaciones/?solo=cuenta')
        .then(({ sin_leer }) => {
          if (!vigente) return
          if (anterior.current !== null && sin_leer > anterior.current) avisarEnElNavegador()
          anterior.current = sin_leer
          setSinLeer(sin_leer)
        })
        .catch(() => {})
    revisar()
    const reloj = setInterval(revisar, SEGUNDOS_ENTRE_REVISIONES * 1000)
    window.addEventListener(EVENTO_AVISOS, revisar)
    return () => {
      vigente = false
      clearInterval(reloj)
      window.removeEventListener(EVENTO_AVISOS, revisar)
    }
  }, [activo])

  return sinLeer
}

function avisarEnElNavegador() {
  try {
    if ('Notification' in window && Notification.permission === 'granted') {
      new Notification('Sistema de Mercado', { body: 'Tenés un aviso nuevo: la caja del día está hecha.' })
    }
  } catch {
    /* el navegador no lo permite: el aviso igual está en la pantalla */
  }
}

// Barra superior con el usuario conectado y su rol (RF-04), presente en todas las pantallas.
export default function Encabezado() {
  const { usuario, logout } = useAuth()
  const { pathname } = useLocation()
  const esDueño = usuario.rol === 'Administrador'
  const sinLeer = useAvisosSinLeer(esDueño)

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
        {esDueño && pathname !== '/avisos' && (
          <Link to="/avisos">
            Avisos{sinLeer > 0 && <span className="contador-avisos">{sinLeer}</span>}
          </Link>
        )}
        <Link to="/cambiar-password">Contraseña</Link>
        <button className="boton-chico" onClick={() => logout()}>Cerrar sesión</button>
      </nav>
    </header>
  )
}
