import { useEffect, useState } from 'react'
import { api } from '../api'
import Encabezado from '../componentes/Encabezado'
import { aFechaISO, deFechaISO, diaCorto, hora } from '../formato'
import { useConsulta } from '../useConsulta'

// Todo lo que pasó en el sistema en un día y horario, y quién lo tenía abierto en ese rato.
// Sirve para saber quién estaba a cargo cuando hubo un problema. Solo dueños.

const GRUPOS = [
  [null, 'Todo'],
  ['VENTAS', 'Ventas'],
  ['CLIENTES', 'Cuentas corrientes'],
  ['GASTOS', 'Gastos'],
  ['COMPRAS', 'Compras a comerciantes'],
  ['STOCK', 'Stock'],
  ['PRODUCTOS', 'Productos'],
  ['ACCESO', 'Ingresos y salidas'],
  ['TURNOS', 'Horarios'],
  ['USUARIOS', 'Usuarios'],
]

const NOMBRE_GRUPO = Object.fromEntries(GRUPOS.filter(([g]) => g))

// Une una fecha "AAAA-MM-DD" con una hora "HH:MM" de acá
function momento(fecha, horaTexto, minutosExtra = 0) {
  const [h, m] = horaTexto.split(':').map(Number)
  const d = deFechaISO(fecha)
  d.setHours(h, m + minutosExtra, 0, 0)
  return d
}

export default function Actividad() {
  const [hoyISO] = useState(() => aFechaISO(new Date()))
  const [fecha, setFecha] = useState(hoyISO)
  const [desde, setDesde] = useState('00:00')
  const [hasta, setHasta] = useState('23:59')
  const [usuario, setUsuario] = useState('')
  const [grupo, setGrupo] = useState(null)
  const [usuarios, setUsuarios] = useState([])

  useEffect(() => {
    api('/api/usuarios/').then(setUsuarios).catch(() => {})
  }, [])

  const horarioValido = Boolean(fecha && desde && hasta && desde <= hasta)

  let ruta = null
  if (horarioValido) {
    const q = new URLSearchParams({
      desde: momento(fecha, desde).toISOString(),
      hasta: momento(fecha, hasta, 1).toISOString(), // +1 minuto: "hasta las 23:59" incluye ese minuto
    })
    if (usuario) q.set('usuario', usuario)
    if (grupo) q.set('grupo', grupo)
    ruta = `/api/actividad/?${q}`
  }
  const { datos, error } = useConsulta(ruta) // datos null = cargando

  const elegirDia = (diasAtras) => {
    const d = new Date()
    d.setDate(d.getDate() - diasAtras)
    setFecha(aFechaISO(d))
    setDesde('00:00')
    setHasta('23:59')
  }

  const ultimaHora = () => {
    const ahora = new Date()
    const antes = new Date(ahora.getTime() - 60 * 60 * 1000)
    const texto = (d) => `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
    setFecha(aFechaISO(ahora))
    // Si la última hora cruza las 00:00, se muestra desde que empezó el día de hoy
    setDesde(aFechaISO(antes) === aFechaISO(ahora) ? texto(antes) : '00:00')
    setHasta(texto(ahora))
  }

  return (
    <>
      <Encabezado />
      <main className="contenedor">
        <h1>Actividad del sistema</h1>
        <p className="subtitulo">
          Todo lo que se hizo en un día y horario, y quién tenía el sistema abierto en ese momento.
        </p>

        <div className="filtros">
          <label>Día <input type="date" value={fecha} max={hoyISO} onChange={(e) => setFecha(e.target.value)} /></label>
          <label>Desde las <input type="time" value={desde} onChange={(e) => setDesde(e.target.value)} /></label>
          <label>Hasta las <input type="time" value={hasta} onChange={(e) => setHasta(e.target.value)} /></label>
          <label>
            Persona
            <select value={usuario} onChange={(e) => setUsuario(e.target.value)}>
              <option value="">Todas</option>
              {usuarios.map((u) => <option key={u.id} value={u.id}>{u.nombre_completo}</option>)}
            </select>
          </label>
        </div>
        <div className="botones atajos">
          <button className="boton-texto" onClick={() => elegirDia(0)}>Hoy</button>
          <button className="boton-texto" onClick={() => elegirDia(1)}>Ayer</button>
          <button className="boton-texto" onClick={ultimaHora}>Última hora</button>
        </div>

        <div className="chips" role="tablist" aria-label="Tipo de actividad">
          {GRUPOS.map(([valor, texto]) => (
            <button key={texto} role="tab" aria-selected={grupo === valor} onClick={() => setGrupo(valor)}>{texto}</button>
          ))}
        </div>

        {!horarioValido ? (
          <p className="mensaje-error" role="alert">Elegí el día, y que la hora «desde» sea anterior a la hora «hasta».</p>
        ) : error ? (
          <p className="mensaje-error" role="alert">{error}</p>
        ) : datos === null ? (
          <p className="subtitulo">Cargando…</p>
        ) : (
          <>
            <section className="bloque">
              <h2>Quién tenía el sistema abierto</h2>
              {datos.de_turno.length === 0 ? (
                <p className="texto-suave">
                  Ningún empleado ni encargado tenía la sesión abierta en ese horario. (Los dueños no llevan turno.)
                </p>
              ) : (
                <ul className="lista-usuarios">
                  {datos.de_turno.map((t) => (
                    <li key={t.id} className="tarjeta fila-usuario">
                      <strong>{t.usuario.nombre} <span className={`rol rol-${t.usuario.rol.toLowerCase()}`}>· {t.usuario.rol}</span></strong>
                      <span>
                        {diaCorto(t.inicio)} · de {hora(t.inicio)} a {t.fin ? hora(t.fin) : 'ahora (sigue conectado)'}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="bloque">
              <h2>Qué se hizo ({datos.eventos.length}{datos.hay_mas ? '+' : ''})</h2>
              {datos.eventos.length === 0 ? (
                <p className="texto-suave">No hubo actividad con esos filtros.</p>
              ) : (
                <ul className="linea-de-tiempo">
                  {datos.eventos.map((e, i) => (
                    <li key={i} className="tarjeta">
                      <time>{hora(e.fecha_hora)}</time>
                      <div className="datos-usuario">
                        <strong>
                          {e.titulo}{' '}
                          <span className={`etiqueta etiqueta-${e.grupo.toLowerCase()}`}>{NOMBRE_GRUPO[e.grupo]}</span>
                        </strong>
                        <span>{e.quien.nombre}</span>
                        {e.detalle && <small className="texto-suave">{e.detalle}</small>}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
              {datos.hay_mas && (
                <p className="subtitulo">Hay más actividad de la que se muestra. Achicá el horario para verla toda.</p>
              )}
            </section>
          </>
        )}
      </main>
    </>
  )
}
