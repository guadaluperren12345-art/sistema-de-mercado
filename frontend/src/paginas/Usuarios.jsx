import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth/AuthContext'
import ConfirmarBaja from '../componentes/ConfirmarBaja'
import Encabezado from '../componentes/Encabezado'

// Lista de usuarios con altas, bajas y reactivaciones (RF-08, RF-10, RF-12). Solo dueños.

const fecha = (iso) =>
  iso ? new Date(iso).toLocaleString('es-AR', { dateStyle: 'short', timeStyle: 'short' }) : 'Nunca ingresó'

export default function Usuarios() {
  const { usuario: yo } = useAuth()
  const [usuarios, setUsuarios] = useState([])
  const [verActivos, setVerActivos] = useState(true)
  const [busqueda, setBusqueda] = useState('')
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState('')
  const [aviso, setAviso] = useState('')
  const [dandoDeBaja, setDandoDeBaja] = useState(null) // id del usuario que se está por dar de baja

  useEffect(() => {
    api('/api/usuarios/')
      .then(setUsuarios)
      .catch((err) => setError(err.message))
      .finally(() => setCargando(false))
  }, [])

  const actualizar = (u) => setUsuarios((lista) => lista.map((x) => (x.id === u.id ? u : x)))

  const darDeBaja = async (u, motivo) => {
    setError('')
    try {
      actualizar(await api(`/api/usuarios/${u.id}/desactivar/`, { metodo: 'POST', datos: { motivo } }))
      setDandoDeBaja(null)
      setAviso(`${u.nombre_completo} fue dado de baja. Ya no puede ingresar al sistema.`)
    } catch (err) {
      setError(err.message)
    }
  }

  const reactivar = async (u) => {
    setError('')
    try {
      actualizar(await api(`/api/usuarios/${u.id}/reactivar/`, { metodo: 'POST' }))
      setAviso(`${u.nombre_completo} fue reactivado y puede volver a ingresar.`)
    } catch (err) {
      setError(err.message)
    }
  }

  // RF-96: el dueño decide qué encargados pueden cargar y corregir clientes de cuenta corriente
  const permisoClientes = async (u, permitir) => {
    setError('')
    try {
      actualizar(await api(`/api/usuarios/${u.id}/permiso-clientes/`, { metodo: 'POST', datos: { permitir } }))
      setAviso(permitir
        ? `${u.nombre_completo} ahora puede cargar y corregir clientes de cuenta corriente.`
        : `${u.nombre_completo} ya no puede cargar clientes de cuenta corriente.`)
    } catch (err) {
      setError(err.message)
    }
  }

  const texto = busqueda.trim().toLowerCase()
  const visibles = usuarios.filter(
    (u) =>
      u.activo === verActivos &&
      (!texto || `${u.nombre_completo} ${u.nombre_usuario} ${u.dni}`.toLowerCase().includes(texto)),
  )
  const cantidadActivos = usuarios.filter((u) => u.activo).length

  return (
    <>
      <Encabezado />
      <main className="contenedor">
        <div className="titulo-con-accion">
          <div>
            <h1>Usuarios</h1>
            <p className="subtitulo">Personal que puede ingresar al sistema</p>
          </div>
          <Link to="/usuarios/nuevo" className="boton">+ Nuevo usuario</Link>
        </div>

        <div className="pestanas" role="tablist">
          <button role="tab" aria-selected={verActivos} onClick={() => setVerActivos(true)}>
            Activos ({cantidadActivos})
          </button>
          <button role="tab" aria-selected={!verActivos} onClick={() => setVerActivos(false)}>
            Dados de baja ({usuarios.length - cantidadActivos})
          </button>
        </div>

        <input
          type="search"
          className="buscador"
          placeholder="Buscar por nombre, usuario o DNI"
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
        />

        {aviso && (
          <p className="mensaje-ok" role="status">
            {aviso} <button className="boton-texto" onClick={() => setAviso('')}>Cerrar</button>
          </p>
        )}
        {error && <p className="mensaje-error" role="alert">{error}</p>}

        {cargando ? (
          <p className="subtitulo">Cargando…</p>
        ) : visibles.length === 0 ? (
          <p className="subtitulo">
            {texto ? 'Ningún usuario coincide con la búsqueda.' : verActivos ? 'No hay usuarios activos.' : 'No hay usuarios dados de baja.'}
          </p>
        ) : (
          <ul className="lista-usuarios">
            {visibles.map((u) => (
              <li key={u.id} className="tarjeta fila-usuario">
                <div className="datos-usuario">
                  <strong>
                    {u.nombre_completo}
                    {u.id === yo.id && <span className="etiqueta">Vos</span>}
                    {u.bloqueado && <span className="etiqueta etiqueta-roja">Bloqueado</span>}
                  </strong>
                  <span>
                    <span className={`rol rol-${u.rol.toLowerCase()}`}>{u.rol}</span> · usuario <b>{u.nombre_usuario}</b> · DNI {u.dni}
                  </span>
                  <small>Último ingreso: {fecha(u.ultimo_acceso)}</small>
                  {u.rol === 'Encargado' && u.activo && (
                    <label className="permiso-usuario">
                      <input type="checkbox" className="casilla" checked={u.puede_gestionar_clientes}
                        onChange={(e) => permisoClientes(u, e.target.checked)} />
                      Puede cargar clientes de cuenta corriente
                    </label>
                  )}
                </div>

                {u.activo ? (
                  u.id !== yo.id &&
                  (dandoDeBaja === u.id ? (
                    <ConfirmarBaja
                      mensaje={<>¿Dar de baja a <b>{u.nombre}</b>? No va a poder ingresar más. Su historial se conserva y se puede reactivar.</>}
                      onConfirmar={(motivo) => darDeBaja(u, motivo)}
                      onCancelar={() => setDandoDeBaja(null)}
                    />
                  ) : (
                    <button className="boton-peligro" onClick={() => { setAviso(''); setDandoDeBaja(u.id) }}>
                      Dar de baja
                    </button>
                  ))
                ) : (
                  <button className="boton-secundario" onClick={() => reactivar(u)}>Reactivar</button>
                )}
              </li>
            ))}
          </ul>
        )}
      </main>
    </>
  )
}
