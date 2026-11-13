import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth/AuthContext'
import Encabezado from '../componentes/Encabezado'
import Recibo from '../componentes/Recibo'
import { imprimirRecibo, leerConfig } from '../dispositivos'
import { aFechaISO, diaCorto, hora, pesos } from '../formato'
import { useConsulta } from '../useConsulta'

// Buzón de recibos: los de hoy y los de la semana pasada, para verlos, reimprimirlos o anularlos.
// Se limpia solo cada domingo (la venta queda guardada para los reportes; solo sale del buzón).
// Dueños y encargados ven todos; un empleado ve los suyos.

const FILTROS = [['hoy', 'Hoy'], ['ayer', 'Ayer'], ['todo', 'Toda la semana']]

function diaDeHace(dias) {
  const d = new Date()
  d.setDate(d.getDate() - dias)
  return aFechaISO(d)
}

export default function Recibos() {
  const { usuario } = useAuth()
  const puedeAnular = usuario.rol !== 'Empleado'
  const [config] = useState(leerConfig)
  const [hoy] = useState(() => diaDeHace(0))
  const [ayer] = useState(() => diaDeHace(1))
  const [filtro, setFiltro] = useState('hoy')
  const [busqueda, setBusqueda] = useState('')
  const [elegido, setElegido] = useState(null) // id del recibo abierto
  const [anulando, setAnulando] = useState(false)
  const [motivo, setMotivo] = useState('')
  const [error, setError] = useState('')
  const [aviso, setAviso] = useState('')
  const [version, setVersion] = useState(0)

  const dia = filtro === 'hoy' ? hoy : filtro === 'ayer' ? ayer : null
  const consulta = useConsulta(`/api/ventas/${dia ? `?desde=${dia}&hasta=${dia}` : ''}`, version)
  const ventas = consulta.datos // null = cargando

  const texto = busqueda.trim().toLowerCase()
  const visibles = (ventas ?? []).filter(
    (v) =>
      !texto ||
      v.numero.includes(texto) ||
      String(Number(v.numero)) === texto ||
      v.vendedor.toLowerCase().includes(texto) ||
      v.items.some((i) => i.nombre.toLowerCase().includes(texto)),
  )
  const vigentes = visibles.filter((v) => !v.anulada)
  const anulados = visibles.filter((v) => v.anulada && !v.reemplazada_por).length
  const totalVisible = vigentes.reduce((suma, v) => suma + Number(v.total), 0)
  const abierto = (ventas ?? []).find((v) => v.id === elegido)

  const abrir = (id) => {
    setElegido(id === elegido ? null : id)
    setAnulando(false)
    setMotivo('')
    setError('')
  }

  const anular = async (e) => {
    e.preventDefault()
    setError('')
    if (!motivo.trim()) return setError('Contá por qué se anula.')
    try {
      const v = await api(`/api/ventas/${elegido}/anular/`, { metodo: 'POST', datos: { motivo } })
      setAviso(`Se anuló el recibo N° ${v.numero}. La mercadería volvió al stock.`)
      setAnulando(false)
      setMotivo('')
      setVersion((n) => n + 1)
    } catch (err) {
      setError(err.message)
    }
  }

  const diaDe = (v) => aFechaISO(new Date(v.fecha_hora))

  return (
    <>
      <Encabezado />
      <main className="contenedor">
        <div className="titulo-con-accion no-imprimir">
          <div>
            <h1>Recibos</h1>
            <p className="subtitulo">
              Los de esta semana y la pasada. El buzón se limpia solo todos los domingos.
            </p>
          </div>
          <Link to="/ventas" className="boton">Ir a vender</Link>
        </div>

        <div className="chips no-imprimir" role="tablist" aria-label="Qué recibos ver">
          {FILTROS.map(([valor, nombre]) => (
            <button key={valor} role="tab" aria-selected={filtro === valor} onClick={() => { setFiltro(valor); setElegido(null) }}>
              {nombre}
            </button>
          ))}
        </div>

        <input type="search" className="buscador no-imprimir" placeholder="Buscar por número de recibo, producto o vendedor"
          value={busqueda} onChange={(e) => setBusqueda(e.target.value)} />

        {aviso && (
          <p className="mensaje-ok no-imprimir" role="status">
            {aviso} <button className="boton-texto" onClick={() => setAviso('')}>Cerrar</button>
          </p>
        )}

        {consulta.error ? (
          <p className="mensaje-error" role="alert">{consulta.error}</p>
        ) : ventas === null ? (
          <p className="subtitulo">Cargando…</p>
        ) : visibles.length === 0 ? (
          <p className="subtitulo">
            {texto ? 'Ningún recibo coincide con la búsqueda.' : filtro === 'todo' ? 'El buzón está vacío.' : 'No hay recibos de ese día.'}
          </p>
        ) : (
          <>
            <p className="total-destacado no-imprimir">
              {vigentes.length} {vigentes.length === 1 ? 'recibo' : 'recibos'} · <b>{pesos(totalVisible)}</b>
              {anulados > 0 && (
                <span className="texto-suave"> · sin contar {anulados === 1 ? '1 anulado' : `${anulados} anulados`}</span>
              )}
            </p>
            <ul className="lista-usuarios">
              {visibles.map((v, i) => {
                // En "Toda la semana" va un título cada vez que cambia el día
                const fecha = diaDe(v)
                const titulo = filtro === 'todo' && (i === 0 || diaDe(visibles[i - 1]) !== fecha)
                return (
                  <li key={v.id} className={elegido === v.id ? '' : 'no-imprimir'}>
                    {titulo && <h2 className="titulo-dia no-imprimir">{fecha === hoy ? 'Hoy' : diaCorto(fecha)}</h2>}
                    <div className={`tarjeta fila-usuario ${v.anulada ? 'recibo-tachado' : ''}`}>
                      <div className="datos-usuario no-imprimir">
                        <strong>
                          N° {v.numero}
                          {v.anulada && (
                            <span className={`etiqueta ${v.reemplazada_por ? '' : 'etiqueta-roja'}`}>
                              {v.reemplazada_por ? `Modificado → N° ${v.reemplazada_por.numero}` : 'Anulado'}
                            </span>
                          )}
                          {v.corrige_a && <span className="etiqueta etiqueta-stock">Corrige al N° {v.corrige_a.numero}</span>}
                        </strong>
                        <span className="texto-suave">
                          {hora(v.fecha_hora)} · {v.vendedor} · {v.medio_pago_texto}{v.cliente && <> · {v.cliente.nombre}</>}
                        </span>
                        <small className="texto-suave">
                          {v.items.slice(0, 3).map((i) => i.nombre).join(', ')}
                          {v.items.length > 3 && ` y ${v.items.length - 3} más`}
                        </small>
                      </div>
                      <div className="stock-cantidad no-imprimir">
                        <b>{pesos(v.total)}</b>
                        <button className="boton-texto" onClick={() => abrir(v.id)}>
                          {elegido === v.id ? 'Cerrar' : 'Ver recibo'}
                        </button>
                      </div>

                      {elegido === v.id && abierto && (
                        <div className="recibo-abierto">
                          <Recibo venta={abierto} config={config} />
                          {abierto.anulada && (
                            <p className="aviso no-imprimir">
                              {abierto.reemplazada_por ? 'Modificado' : 'Anulado'} por {abierto.anulada_por} el {diaCorto(abierto.anulada_en)} a las {hora(abierto.anulada_en)}: {abierto.motivo_anulacion}
                            </p>
                          )}
                          {anulando ? (
                            <form className="confirmar-baja no-imprimir" onSubmit={anular}>
                              <p>¿Anular el recibo <b>N° {abierto.numero}</b>? La mercadería vuelve al stock y la venta deja de sumar. Queda registrado quién lo anuló.</p>
                              <input placeholder="Motivo (ej.: se cobró dos veces)" value={motivo} maxLength={200} autoFocus
                                onChange={(e) => { setMotivo(e.target.value); setError('') }} />
                              {error && <p className="mensaje-error" role="alert">{error}</p>}
                              <div className="botones">
                                <button type="submit" className="boton-peligro">Sí, anular</button>
                                <button type="button" className="boton-secundario" onClick={() => setAnulando(false)}>Cancelar</button>
                              </div>
                            </form>
                          ) : (
                            <div className="botones no-imprimir">
                              <button className="boton-chico" onClick={() => imprimirRecibo(config.ancho)}>Imprimir de nuevo</button>
                              {abierto.puede_corregir && (
                                <Link to={`/ventas?corregir=${abierto.id}`} className="boton boton-chico-enlace">Modificar compra</Link>
                              )}
                              {puedeAnular && !abierto.anulada && (
                                <button className="boton-chico boton-borde" onClick={() => setAnulando(true)}>Anular venta</button>
                              )}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </li>
                )
              })}
            </ul>
            {ventas.length >= 500 && <p className="subtitulo">Se muestran los últimos 500 recibos.</p>}
          </>
        )}
      </main>
    </>
  )
}
