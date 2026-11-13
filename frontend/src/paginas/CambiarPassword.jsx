import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export default function CambiarPassword() {
  const { usuario, cambiarPassword, logout } = useAuth()
  const navigate = useNavigate()
  const [actual, setActual] = useState('')
  const [nueva, setNueva] = useState('')
  const [repetir, setRepetir] = useState('')
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)

  const obligatorio = usuario.debe_cambiar_password

  const enviar = async (e) => {
    e.preventDefault()
    setError('')
    if (nueva !== repetir) {
      setError('Las contraseñas nuevas no coinciden.')
      return
    }
    setEnviando(true)
    try {
      await cambiarPassword(actual, nueva)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <main className="pantalla-centrada">
      <form className="tarjeta formulario" onSubmit={enviar}>
        <h1>Cambiar contraseña</h1>
        {obligatorio && (
          <p className="aviso">
            Hola {usuario.nombre}. Antes de empezar tenés que elegir una contraseña nueva, que solo vos conozcas.
          </p>
        )}

        <label>
          Contraseña actual
          <input type="password" value={actual} onChange={(e) => setActual(e.target.value)}
            autoComplete="current-password" required />
        </label>
        <label>
          Contraseña nueva
          <input type="password" value={nueva} onChange={(e) => setNueva(e.target.value)}
            autoComplete="new-password" required />
          <small>Mínimo 8 caracteres, con al menos una letra y un número.</small>
        </label>
        <label>
          Repetir contraseña nueva
          <input type="password" value={repetir} onChange={(e) => setRepetir(e.target.value)}
            autoComplete="new-password" required />
        </label>

        {error && <p className="mensaje-error" role="alert">{error}</p>}

        <button type="submit" disabled={enviando}>
          {enviando ? 'Guardando…' : 'Guardar contraseña'}
        </button>
        {obligatorio ? (
          <button type="button" className="boton-secundario" onClick={logout}>Cerrar sesión</button>
        ) : (
          <button type="button" className="boton-secundario" onClick={() => navigate('/')}>Cancelar</button>
        )}
      </form>
    </main>
  )
}
