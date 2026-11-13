import { useState } from 'react'
import { api } from '../api'
import Encabezado from '../componentes/Encabezado'
import SelectorPeriodo from '../componentes/SelectorPeriodo'
import { aFechaISO, diaCorto, duracion, hora } from '../formato'
import { hoy, parametrosDe } from '../periodo'
import { useConsulta } from '../useConsulta'

// Horarios del personal (RF-25 a RF-28). Solo dueños.
// El horario se cuenta solo: desde que la persona entra con su contraseña hasta que cierra sesión.

// "HH:MM" de un momento, para los campos de hora
const horaDeCampo = (iso) => {
  const d = new Date(iso)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

// Une el día en que empezó el turno con la hora elegida. "00:00" es la medianoche con la que termina ese día.
function momentoDeSalida(turno, horaElegida) {
  const [h, m] = horaElegida.split(':').map(Number)
  const d = new Date(turno.inicio)
  d.setHours(h, m, 0, 0)
  if (h === 0 && m === 0) d.setDate(d.getDate() + 1)
  return d
}

function CorregirSalida({ turno, onListo, onCancelar }) {
  // Sugerencia: si sigue abierto, la hora de ahora; si no, la última vez que usó el sistema
  const [horaSalida, setHoraSalida] = useState(() => horaDeCampo(turno.abierto ? new Date() : turno.ultima_actividad))
  const [nota, setNota] = useState('')
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)

  const enviar = async (e) => {
    e.preventDefault()
    setError('')
    if (!horaSalida) return setError('Elegí la hora de salida.')
    setEnviando(true)
    try {
      const fin = momentoDeSalida(turno, horaSalida).toISOString()
      onListo(await api(`/api/turnos/${turno.id}/corregir/`, { metodo: 'POST', datos: { fin, nota } }))
    } catch (err) {
      setError(err.message)
      setEnviando(false)
    }
  }

  return (
    <form className="panel-stock" onSubmit={enviar} noValidate>
      <strong>
        {turno.abierto ? 'Cerrar el turno de' : 'Corregir la salida de'} {turno.usuario.nombre} · {diaCorto(turno.inicio)}
      </strong>
      <small className="texto-suave">
        Entró a las {hora(turno.inicio)}. Último movimiento en el sistema: {hora(turno.ultima_actividad)}.
      </small>
      <label>
        ¿A qué hora se fue?
        <input type="time" value={horaSalida} required autoFocus onChange={(e) => setHoraSalida(e.target.value)} />
      </label>
      <label>
        Nota <small>(opcional)</small>
        <input value={nota} maxLength={300} placeholder="Ej.: se olvidó de cerrar sesión"
          onChange={(e) => setNota(e.target.value)} />
      </label>
      {error && <p className="mensaje-error" role="alert">{error}</p>}
      <div className="botones">
        <button type="submit" disabled={enviando}>{enviando ? 'Guardando…' : 'Guardar hora de salida'}</button>
        <button type="button" className="boton-secundario" onClick={onCancelar}>Cancelar</button>
      </div>
    </form>
  )
}

// Cómo terminó el turno, en palabras
function Cierre({ turno }) {
  if (turno.abierto) return <span className="etiqueta etiqueta-verde sin-margen">Trabajando ahora</span>
  return (
    <>
      {turno.tipo_cierre !== 'USUARIO' && (
        <span className={`etiqueta sin-margen ${turno.para_revisar ? 'etiqueta-roja' : ''}`}>{turno.tipo_cierre_texto}</span>
      )}
      {turno.corregido_por && (
        <small className="texto-suave">
          {' '}
          {turno.fin_original && turno.fin_original !== turno.fin
            ? `Salida corregida por ${turno.corregido_por} (antes ${hora(turno.fin_original)})`
            : `Revisado por ${turno.corregido_por}`}
          {turno.nota && ` · ${turno.nota}`}
        </small>
      )}
    </>
  )
}

export default function Horarios() {
  const [tipo, setTipo] = useState('semana')
  const [ancla, setAncla] = useState(hoy())
  const [corrigiendo, setCorrigiendo] = useState(null) // zona + id del turno (a: ahora, r: para revisar, d: detalle)
  const [persona, setPersona] = useState(null) // id de la persona con el detalle abierto
  const [errorAccion, setError] = useState('')
  const [aviso, setAviso] = useState('')
  const [version, setVersion] = useState(0) // al sumar 1 se vuelven a pedir los turnos

  const consultaAbiertos = useConsulta('/api/turnos/?estado=abiertos', version)
  const consultaRevisar = useConsulta('/api/turnos/?estado=revisar', version)
  const consultaPeriodo = useConsulta(`/api/turnos/?${parametrosDe(tipo, ancla)}`, version)
  const abiertos = consultaAbiertos.datos ?? []
  const paraRevisar = consultaRevisar.datos ?? []
  const turnos = consultaPeriodo.datos // null = cargando
  const error = errorAccion || consultaPeriodo.error || consultaAbiertos.error

  const guardado = (turno, mensaje) => {
    setCorrigiendo(null)
    setAviso(mensaje ?? `Se guardó el horario de ${turno.usuario.nombre}.`)
    setVersion((v) => v + 1)
  }

  const confirmar = async (turno) => {
    setError('')
    try {
      const t = await api(`/api/turnos/${turno.id}/corregir/`, { metodo: 'POST', datos: {} })
      guardado(t, `Se confirmó el horario de ${t.usuario.nombre} hasta las 00:00.`)
    } catch (err) {
      setError(err.message)
    }
  }

  // Totales por persona del período
  const personas = Object.values(
    (turnos ?? []).reduce((mapa, t) => {
      const p = (mapa[t.usuario.id] ??= { ...t.usuario, minutos: 0, turnos: [], dias: new Set() })
      p.minutos += t.minutos
      p.turnos.push(t)
      p.dias.add(aFechaISO(new Date(t.inicio)))
      return mapa
    }, {}),
  ).sort((a, b) => a.nombre.localeCompare(b.nombre))
  const totalMinutos = personas.reduce((suma, p) => suma + p.minutos, 0)

  return (
    <>
      <Encabezado />
      <main className="contenedor">
        <h1>Horarios del personal</h1>
        <p className="subtitulo">
          El horario se cuenta solo: desde que cada persona entra con su contraseña hasta que cierra sesión.
        </p>

        {aviso && (
          <p className="mensaje-ok" role="status">
            {aviso} <button className="boton-texto" onClick={() => setAviso('')}>Cerrar</button>
          </p>
        )}
        {error && <p className="mensaje-error" role="alert">{error}</p>}

        <section className="bloque">
          <h2>Trabajando ahora</h2>
          {abiertos.length === 0 ? (
            <p className="texto-suave">Nadie tiene la sesión abierta en este momento.</p>
          ) : (
            <ul className="lista-usuarios">
              {abiertos.map((t) => (
                <li key={t.id} className="tarjeta fila-usuario borde-verde">
                  <div className="datos-usuario">
                    <strong>{t.usuario.nombre} <span className={`rol rol-${t.usuario.rol.toLowerCase()}`}>· {t.usuario.rol}</span></strong>
                    <span>Entró a las {hora(t.inicio)} · lleva <b>{duracion(t.minutos)}</b></span>
                    <small className="texto-suave">Último movimiento en el sistema: {hora(t.ultima_actividad)}</small>
                  </div>
                  {corrigiendo === `a${t.id}` ? (
                    <CorregirSalida turno={t} onListo={guardado} onCancelar={() => setCorrigiendo(null)} />
                  ) : (
                    <button className="boton-chico boton-borde" onClick={() => { setAviso(''); setCorrigiendo(`a${t.id}`) }}>
                      Cerrar su turno
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        {paraRevisar.length > 0 && (
          <section className="bloque">
            <h2>Para revisar ({paraRevisar.length})</h2>
            <p className="texto-suave">
              Estas personas no cerraron sesión: el sistema les cerró el turno a las 00:00. Indicá a qué hora se fueron en realidad.
            </p>
            <ul className="lista-usuarios">
              {paraRevisar.map((t) => (
                <li key={t.id} className="tarjeta fila-usuario borde-amarillo">
                  <div className="datos-usuario">
                    <strong>{t.usuario.nombre} · {diaCorto(t.inicio)}</strong>
                    <span>Entró a las {hora(t.inicio)} · el sistema contó {duracion(t.minutos)}</span>
                    <small className="texto-suave">Último movimiento en el sistema: {hora(t.ultima_actividad)}</small>
                  </div>
                  {corrigiendo === `r${t.id}` ? (
                    <CorregirSalida turno={t} onListo={guardado} onCancelar={() => setCorrigiendo(null)} />
                  ) : (
                    <div className="botones">
                      <button className="boton-chico" onClick={() => { setAviso(''); setCorrigiendo(`r${t.id}`) }}>
                        Corregir hora de salida
                      </button>
                      <button className="boton-chico boton-borde" onClick={() => confirmar(t)}>Está bien así</button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}

        <section className="bloque">
          <h2>Horas trabajadas</h2>
          <SelectorPeriodo tipo={tipo} ancla={ancla} onCambiar={(t, a) => { setTipo(t); setAncla(a); setPersona(null) }} />

          {consultaPeriodo.error ? null : turnos === null ? (
            <p className="subtitulo">Cargando…</p>
          ) : personas.length === 0 ? (
            <p className="subtitulo">Nadie trabajó en este período.</p>
          ) : (
            <>
              <p className="total-destacado">Total del período: <b>{duracion(totalMinutos)}</b></p>
              <ul className="lista-usuarios">
                {personas.map((p) => (
                  <li key={p.id} className="tarjeta fila-usuario">
                    <div className="datos-usuario">
                      <strong>{p.nombre} <span className={`rol rol-${p.rol.toLowerCase()}`}>· {p.rol}</span></strong>
                      <span className="texto-suave">
                        {p.dias.size} {p.dias.size === 1 ? 'día' : 'días'} · {p.turnos.length} {p.turnos.length === 1 ? 'ingreso' : 'ingresos'}
                        {p.turnos.some((t) => t.para_revisar) && <span className="etiqueta etiqueta-roja">Falta revisar</span>}
                      </span>
                    </div>
                    <div className="stock-cantidad">
                      <b>{duracion(p.minutos)}</b>
                      <button className="boton-texto" onClick={() => setPersona(persona === p.id ? null : p.id)}>
                        {persona === p.id ? 'Ocultar detalle' : 'Ver detalle'}
                      </button>
                    </div>

                    {persona === p.id && (
                      <ul className="detalle-turnos">
                        {[...p.turnos].reverse().map((t) => (
                          <li key={t.id}>
                            <div>
                              <b>{diaCorto(t.inicio)}</b> · {hora(t.inicio)} a {t.abierto ? 'ahora' : hora(t.fin)} ·{' '}
                              <b>{duracion(t.minutos)}</b> <Cierre turno={t} />
                            </div>
                            {corrigiendo === `d${t.id}` ? (
                              <CorregirSalida turno={t} onListo={guardado} onCancelar={() => setCorrigiendo(null)} />
                            ) : (
                              <button className="boton-texto" onClick={() => { setAviso(''); setCorrigiendo(`d${t.id}`) }}>
                                {t.abierto ? 'Cerrar turno' : 'Corregir salida'}
                              </button>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      </main>
    </>
  )
}
