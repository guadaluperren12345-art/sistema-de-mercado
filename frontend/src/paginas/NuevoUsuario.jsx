import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import Encabezado from '../componentes/Encabezado'

// Alta de un usuario nuevo (RF-08). Solo dueños.

const ROLES = [
  { nombre: 'Empleado', detalle: 'Ventas, cobros, facturas y su turno. No cambia precios.' },
  { nombre: 'Encargado', detalle: 'Lo del empleado, más precios en su turno, mercadería, pagos y anulaciones.' },
  { nombre: 'Administrador', detalle: 'Dueño: acceso total, usuarios y cierres de caja.' },
]

const VACIO = { nombre: '', apellido: '', dni: '', nombre_usuario: '', email: '', rol: 'Empleado', password: '' }

// Contraseña inicial fácil de dictar: palabra + 4 números (cumple RN-06)
const PALABRAS = ['Tomate', 'Lechuga', 'Naranja', 'Zapallo', 'Durazno', 'Cebolla', 'Manzana', 'Pimiento']
function generarPassword() {
  const n = new Uint32Array(2)
  crypto.getRandomValues(n)
  return `${PALABRAS[n[0] % PALABRAS.length]}${String(n[1] % 10000).padStart(4, '0')}`
}

// Sugiere el usuario a partir del nombre: "Juan Pérez" -> "jperez"
function sugerirUsuario(nombre, apellido) {
  const limpio = (t) => t.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]/g, '')
  return `${limpio(nombre).charAt(0)}${limpio(apellido)}`
}

export default function NuevoUsuario() {
  const [datos, setDatos] = useState(() => ({ ...VACIO, password: generarPassword() }))
  const [usuarioEditado, setUsuarioEditado] = useState(false) // si el dueño escribió el usuario a mano
  const [errores, setErrores] = useState({})
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [creado, setCreado] = useState(null)

  const cambiar = (campo) => (e) => {
    const valor = e.target.value
    setDatos((d) => {
      const nuevos = { ...d, [campo]: valor }
      if ((campo === 'nombre' || campo === 'apellido') && !usuarioEditado) {
        nuevos.nombre_usuario = sugerirUsuario(nuevos.nombre, nuevos.apellido)
      }
      return nuevos
    })
    if (campo === 'nombre_usuario') setUsuarioEditado(true)
    setErrores((er) => ({ ...er, [campo]: undefined }))
  }

  const enviar = async (e) => {
    e.preventDefault()
    setError('')
    setErrores({})
    setEnviando(true)
    try {
      const u = await api('/api/usuarios/', { metodo: 'POST', datos })
      setCreado({ ...u, password: datos.password })
    } catch (err) {
      if (err.status === 400 && err.datos && !err.datos.detail) {
        setErrores(err.datos)
        setError('Revisá los datos marcados.')
      } else {
        setError(err.message)
      }
    } finally {
      setEnviando(false)
    }
  }

  const otro = () => {
    setDatos({ ...VACIO, password: generarPassword() })
    setUsuarioEditado(false)
    setCreado(null)
  }

  if (creado) {
    return (
      <>
        <Encabezado />
        <main className="pantalla-centrada sin-alto">
          <div className="tarjeta formulario">
            <h1>Usuario creado</h1>
            <p className="mensaje-ok">
              {creado.nombre_completo} ya puede ingresar como <b>{creado.rol}</b>.
            </p>
            <p>Pasale estos datos. En su primer ingreso el sistema le va a pedir que elija una contraseña propia.</p>
            <dl className="credenciales">
              <dt>Usuario</dt>
              <dd>{creado.nombre_usuario}</dd>
              <dt>Contraseña inicial</dt>
              <dd>{creado.password}</dd>
            </dl>
            <button onClick={otro}>Cargar otro usuario</button>
            <Link to="/usuarios" className="boton boton-secundario">Volver a la lista</Link>
          </div>
        </main>
      </>
    )
  }

  const errorDe = (campo) =>
    errores[campo] && <span className="error-campo">{[errores[campo]].flat().join(' ')}</span>

  return (
    <>
      <Encabezado />
      <main className="pantalla-centrada sin-alto">
        <form className="tarjeta formulario" onSubmit={enviar} noValidate>
          <h1>Nuevo usuario</h1>
          <p className="subtitulo">Completá los datos de la persona que empieza a trabajar</p>

          <label>
            Nombre
            <input value={datos.nombre} onChange={cambiar('nombre')} autoFocus required maxLength={50} />
            {errorDe('nombre')}
          </label>
          <label>
            Apellido
            <input value={datos.apellido} onChange={cambiar('apellido')} required maxLength={50} />
            {errorDe('apellido')}
          </label>
          <label>
            DNI
            <input value={datos.dni} onChange={cambiar('dni')} inputMode="numeric" required maxLength={10}
              placeholder="Solo números" />
            {errorDe('dni')}
          </label>
          <label>
            Nombre de usuario
            <input value={datos.nombre_usuario} onChange={cambiar('nombre_usuario')} required maxLength={50}
              autoCapitalize="none" autoComplete="off" />
            <small>Con este nombre va a ingresar. Sin espacios ni acentos.</small>
            {errorDe('nombre_usuario')}
          </label>
          <label>
            Email <small>(opcional)</small>
            <input type="email" value={datos.email} onChange={cambiar('email')} maxLength={100} />
            {errorDe('email')}
          </label>

          <fieldset className="opciones-rol">
            <legend>Rol</legend>
            {ROLES.map((r) => (
              <label key={r.nombre} className={`opcion ${datos.rol === r.nombre ? 'elegida' : ''}`}>
                <input type="radio" name="rol" value={r.nombre} checked={datos.rol === r.nombre}
                  onChange={cambiar('rol')} />
                <span>
                  <b>{r.nombre}</b>
                  <small>{r.detalle}</small>
                </span>
              </label>
            ))}
            {errorDe('rol')}
          </fieldset>

          <label>
            Contraseña inicial
            <div className="campo-password">
              <input value={datos.password} onChange={cambiar('password')} required autoComplete="off" />
              <button type="button" className="boton-texto"
                onClick={() => setDatos((d) => ({ ...d, password: generarPassword() }))}>
                Otra
              </button>
            </div>
            <small>Se la pasás a la persona; en su primer ingreso la cambia por una propia.</small>
            {errorDe('password')}
          </label>

          {error && <p className="mensaje-error" role="alert">{error}</p>}

          <button type="submit" disabled={enviando}>{enviando ? 'Guardando…' : 'Crear usuario'}</button>
          <Link to="/usuarios" className="boton boton-secundario">Cancelar</Link>
        </form>
      </main>
    </>
  )
}
