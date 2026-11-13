import { useRef, useState } from 'react'
import { api } from '../api'
import { useAuth } from '../auth/AuthContext'
import ConfirmarBaja from '../componentes/ConfirmarBaja'
import Encabezado from '../componentes/Encabezado'
import { aFechaISO, diaCorto, hora, leerNumero, pesos } from '../formato'
import { useConsulta } from '../useConsulta'

// Lista de gastos (RF-106 a RF-111). La usan todos, como una hoja de anotaciones:
// cada renglón es un monto y para qué fue. El total del día se resta solo en el cierre de las 00:00.
// Un gasto no se borra: si se anotó mal, se anula (lo puede hacer quien lo anotó, ese mismo día,
// o un encargado o dueño). Dueños y encargados pueden mirar también los días anteriores.

export default function Gastos() {
  const { usuario } = useAuth()
  const veOtrosDias = usuario.rol !== 'Empleado'
  const [hoy] = useState(() => aFechaISO(new Date()))
  const [fecha, setFecha] = useState(hoy)
  const [version, setVersion] = useState(0) // al cambiar, vuelve a pedir la lista
  const { datos, error: errorLista } = useConsulta(`/api/gastos/?fecha=${fecha}`, version)
  const [monto, setMonto] = useState('')
  const [proposito, setProposito] = useState('')
  const [errores, setErrores] = useState({})
  const [error, setError] = useState('')
  const [aviso, setAviso] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [anulando, setAnulando] = useState(null) // id del gasto que se está por anular
  const campoMonto = useRef(null)

  const esHoy = fecha === hoy
  const gastos = datos?.gastos ?? []

  const anotar = async (e) => {
    e.preventDefault()
    setError('')
    setAviso('')
    const n = leerNumero(monto)
    const errs = {}
    if (n === null || n <= 0) errs.monto = 'Escribí el monto con números, mayor a 0.'
    if (proposito.trim().length < 3) errs.proposito = 'Anotá para qué fue el gasto.'
    setErrores(errs)
    if (Object.keys(errs).length) return

    setEnviando(true)
    try {
      const g = await api('/api/gastos/', { metodo: 'POST', datos: { monto: n.toFixed(2), proposito } })
      setMonto('')
      setProposito('')
      setAviso(`Anotado: −${pesos(g.monto)} · ${g.proposito}.`)
      setFecha(hoy) // un gasto nuevo siempre es de hoy
      setVersion((v) => v + 1)
      campoMonto.current?.focus() // listo para anotar el siguiente
    } catch (err) {
      if (err.status === 400 && err.datos && !err.datos.detail) setErrores(err.datos)
      else setError(err.message)
    } finally {
      setEnviando(false)
    }
  }

  const anular = async (g, motivo) => {
    setError('')
    try {
      await api(`/api/gastos/${g.id}/anular/`, { metodo: 'POST', datos: { motivo } })
      setAnulando(null)
      setAviso(`Se anuló el gasto de ${pesos(g.monto)} (${g.proposito}). Ya no se resta en el cierre.`)
      setVersion((v) => v + 1)
    } catch (err) {
      setError(err.message)
    }
  }

  const errorDe = (campo) => errores[campo] && <span className="error-campo">{[errores[campo]].flat().join(' ')}</span>

  return (
    <>
      <Encabezado />
      <main className="contenedor">
        <h1>Gastos</h1>
        <p className="subtitulo">
          Anotá cada gasto con su monto y para qué fue. El total del día se resta solo en el cierre de las 00:00.
        </p>

        <form className="tarjeta anotar-gasto" onSubmit={anotar} noValidate>
          <label>
            Monto
            <input ref={campoMonto} value={monto} inputMode="decimal" autoComplete="off" autoFocus placeholder="Ej.: 2500"
              onChange={(e) => { setMonto(e.target.value); setErrores({ ...errores, monto: undefined }) }} />
            {errorDe('monto')}
          </label>
          <label>
            ¿Para qué fue?
            <input value={proposito} maxLength={200} autoComplete="off" placeholder="Ej.: bolsas, hielo, flete, arreglo de la heladera"
              onChange={(e) => { setProposito(e.target.value); setErrores({ ...errores, proposito: undefined }) }} />
            {errorDe('proposito')}
          </label>
          <button type="submit" disabled={enviando}>{enviando ? 'Anotando…' : 'Anotar gasto'}</button>
        </form>

        {aviso && (
          <p className="mensaje-ok" role="status">
            {aviso} <button className="boton-texto" onClick={() => setAviso('')}>Cerrar</button>
          </p>
        )}
        {(error || errorLista) && <p className="mensaje-error" role="alert">{error || errorLista}</p>}

        <div className="titulo-con-accion titulo-lista-gastos">
          <h2>{esHoy ? 'Gastos de hoy' : `Gastos del ${diaCorto(fecha)}`}</h2>
          {veOtrosDias && (
            <div className="campo-con-boton">
              <input type="date" value={fecha} max={hoy} aria-label="Ver los gastos de otro día"
                onChange={(e) => { if (e.target.value) { setFecha(e.target.value); setAnulando(null) } }} />
              {!esHoy && <button className="boton-borde" onClick={() => setFecha(hoy)}>Hoy</button>}
            </div>
          )}
        </div>

        {datos === null && !errorLista ? (
          <p className="subtitulo">Cargando…</p>
        ) : gastos.length === 0 ? (
          <p className="subtitulo">{esHoy ? 'Todavía no se anotó ningún gasto hoy.' : 'Ese día no se anotaron gastos.'}</p>
        ) : (
          <ul className="lista-gastos tarjeta">
            {gastos.map((g) => (
              <li key={g.id} className={g.anulado ? 'gasto-anulado' : ''}>
                <div className="renglon-gasto">
                  <b className="monto-gasto">−{pesos(g.monto)}</b>
                  <div className="datos-usuario">
                    <span className="proposito-gasto">{g.proposito}</span>
                    <small className="texto-suave">
                      {hora(g.fecha_hora)} · {g.usuario}
                      {g.anulado && <> · anulado por {g.anulado_por}{g.motivo_anulacion && `: ${g.motivo_anulacion}`}</>}
                    </small>
                  </div>
                  {g.anulado
                    ? <span className="etiqueta etiqueta-roja">Anulado</span>
                    : g.puede_anular && anulando !== g.id && (
                      <button className="boton-texto" onClick={() => { setAviso(''); setAnulando(g.id) }}>Anular</button>
                    )}
                </div>
                {anulando === g.id && (
                  <ConfirmarBaja
                    mensaje={<>¿Anular el gasto de <b>{pesos(g.monto)}</b> ({g.proposito})? Queda en la lista tachado y deja de restarse.</>}
                    textoBoton="Sí, anular"
                    onConfirmar={(motivo) => anular(g, motivo)}
                    onCancelar={() => setAnulando(null)}
                  />
                )}
              </li>
            ))}
            <li className="total-gastos">
              <span>
                Total de gastos {esHoy ? 'de hoy' : 'del día'} <small className="texto-suave">({datos.cantidad} {datos.cantidad === 1 ? 'gasto' : 'gastos'})</small>
              </span>
              <b>{Number(datos.total) > 0 ? '−' : ''}{pesos(datos.total)}</b>
            </li>
          </ul>
        )}

        <p className="subtitulo nota-precios">
          Los gastos salen de la plata de la caja: por eso se restan de lo que entró en el día y del efectivo que debería haber.
          {usuario.rol === 'Administrador' && ' La cuenta final está en «Resumen y cierre del día».'}
        </p>
      </main>
    </>
  )
}
