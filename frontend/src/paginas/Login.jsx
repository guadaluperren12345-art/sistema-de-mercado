import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export default function Login() {
  const { usuario, login, avisoSesion } = useAuth()
  const navigate = useNavigate()
  const [nombreUsuario, setNombreUsuario] = useState('')
  const [password, setPassword] = useState('')
  const [verPassword, setVerPassword] = useState(false)
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)

  if (usuario) return <Navigate to="/" replace />

  const enviar = async (e) => {
    e.preventDefault()
    setError('')
    setEnviando(true)
    try {
      const u = await login(nombreUsuario.trim(), password)
      navigate(u.debe_cambiar_password ? '/cambiar-password' : '/', { replace: true })
    } catch (err) {
      setError(err.message)
      setPassword('')
    } finally {
      setEnviando(false)
    }
  }

  return (
    <main className="pantalla-centrada">
      <form className="tarjeta formulario" onSubmit={enviar}>
        <h1>Sistema de Mercado</h1>
        <p className="subtitulo">Ingresá con tu usuario y contraseña</p>
        {avisoSesion && !error && <p className="aviso" role="status">{avisoSesion}</p>}

        <label>
          Usuario
          <input
            value={nombreUsuario}
            onChange={(e) => setNombreUsuario(e.target.value)}
            autoComplete="username"
            autoCapitalize="none"
            autoFocus
            required
          />
        </label>

        <label>
          Contraseña
          <div className="campo-password">
            <input
              type={verPassword ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
            <button
              type="button"
              className="boton-texto"
              onClick={() => setVerPassword((v) => !v)}
              aria-label={verPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'}
            >
              {verPassword ? 'Ocultar' : 'Ver'}
            </button>
          </div>
        </label>

        {error && <p className="mensaje-error" role="alert">{error}</p>}

        <button type="submit" disabled={enviando}>
          {enviando ? 'Ingresando…' : 'Ingresar'}
        </button>
      </form>
    </main>
  )
}
