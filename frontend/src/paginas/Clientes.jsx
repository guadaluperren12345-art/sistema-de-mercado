import { useEffect, useState } from 'react'
import { api } from '../api'
import { useAuth } from '../auth/AuthContext'
import ConfirmarBaja from '../componentes/ConfirmarBaja'
import Encabezado from '../componentes/Encabezado'
import { imprimirRecibo, leerConfig } from '../dispositivos'
import { fechaHora, leerNumero, pesos } from '../formato'

// Cuentas corrientes («fiado», RF-95 a RF-105).
// Todos ven a los clientes y cobran pagos. Cargar y corregir clientes: los dueños y los encargados
// que un dueño autorizó (en Usuarios). Los límites de fiado y los ajustes: solo los dueños.
// Para fiar se va a Vender y se elige «Cuenta corriente» como forma de pago.

const MEDIOS = [
  ['EFECTIVO', 'Efectivo'],
  ['DEBITO', 'Débito'],
  ['CREDITO', 'Crédito'],
  ['TRANSFERENCIA', 'Transferencia'],
  ['QR', 'QR'],
]

const VACIO = { nombre: '', dni: '', telefono: '', direccion: '', nota: '', limite: '' }
const aTexto = (n) => (n == null ? '' : String(Number(n)).replace('.', ','))
const conSigno = (importe) => `${Number(importe) > 0 ? '+' : '−'}${pesos(Math.abs(Number(importe)))}`

// Texto del saldo: «Debe $ 5.000», «No debe nada» o «A favor $ 300»
function textoSaldo(saldo) {
  const n = Number(saldo)
  if (n > 0) return `Debe ${pesos(n)}`
  return n < 0 ? `A favor ${pesos(-n)}` : 'No debe nada'
}

// Comprobante de un pago, con el mismo formato que el recibo (sale por la misma impresora)
function Comprobante({ movimiento, config }) {
  return (
    <div className={`recibo recibo-${config.ancho}`}>
      <div className="recibo-centro">
        <strong className="recibo-negocio">{config.negocio || 'Mercado'}</strong>
        {config.direccion && <span>{config.direccion}</span>}
      </div>
      <div className="recibo-linea" />
      <div className="recibo-centro"><strong>PAGO DE CUENTA CORRIENTE</strong></div>
      <div className="recibo-fila"><span>Comprobante N° {movimiento.numero}</span><span>{fechaHora(movimiento.fecha_hora)}</span></div>
      <div>Cliente: {movimiento.cliente_nombre}</div>
      <div>Recibió: {movimiento.usuario}</div>
      <div className="recibo-linea" />
      <div className="recibo-fila recibo-total"><span>PAGÓ</span><span>{pesos(-Number(movimiento.importe))}</span></div>
      <div className="recibo-fila"><span>Pago</span><span>{movimiento.medio_pago_texto}</span></div>
      <div className="recibo-fila"><span>Saldo de la cuenta</span><span>{textoSaldo(movimiento.saldo_resultante)}</span></div>
      <div className="recibo-linea" />
      <div className="recibo-centro">
        {config.pie && <span>{config.pie}</span>}
        <span className="recibo-chico">Comprobante no válido como factura</span>
      </div>
    </div>
  )
}

export default function Clientes() {
  const { usuario } = useAuth()
  const esDueño = usuario.rol === 'Administrador'
  const gestiona = Boolean(usuario.gestiona_clientes)
  const [config] = useState(leerConfig)
  const [clientes, setClientes] = useState([])
  const [limiteGeneral, setLimiteGeneral] = useState(null)
  const [cargando, setCargando] = useState(true)
  const [verActivos, setVerActivos] = useState(true)
  const [soloDeudores, setSoloDeudores] = useState(false)
  const [busqueda, setBusqueda] = useState('')
  const [panel, setPanel] = useState(null) // { tipo: 'pago' | 'cuenta' | 'editar' | 'baja' | 'nuevo' | 'limite', id }
  const [form, setForm] = useState(VACIO) // alta y edición
  const [errores, setErrores] = useState({})
  const [pago, setPago] = useState({ importe: '', medio: 'EFECTIVO' })
  const [ajuste, setAjuste] = useState({ suma: true, importe: '', motivo: '' })
  const [textoLimite, setTextoLimite] = useState('')
  const [movimientos, setMovimientos] = useState(null)
  const [comprobante, setComprobante] = useState(null)
  const [enviando, setEnviando] = useState(false)
  const [aviso, setAviso] = useState('')
  const [error, setError] = useState('')

  const cargar = () =>
    Promise.all([api('/api/clientes/'), api('/api/cuentas/configuracion/')]).then(([lista, c]) => {
      setClientes(lista)
      setLimiteGeneral(c.limite_general)
    })

  useEffect(() => {
    cargar().catch((err) => setError(err.message)).finally(() => setCargando(false))
  }, [])

  const abrir = (tipo, cliente) => {
    setError('')
    setAviso('')
    setErrores({})
    setPanel({ tipo, id: cliente?.id ?? null })
    if (tipo === 'nuevo') setForm(VACIO)
    if (tipo === 'editar') {
      setForm({
        nombre: cliente.nombre, dni: cliente.dni ?? '', telefono: cliente.telefono ?? '',
        direccion: cliente.direccion ?? '', nota: cliente.nota ?? '', limite: aTexto(cliente.limite),
      })
    }
    if (tipo === 'pago') setPago({ importe: aTexto(cliente.saldo), medio: 'EFECTIVO' })
    if (tipo === 'limite') setTextoLimite(aTexto(limiteGeneral))
    if (tipo === 'cuenta') {
      setMovimientos(null)
      setAjuste({ suma: true, importe: '', motivo: '' })
      api(`/api/clientes/${cliente.id}/movimientos/`).then(setMovimientos).catch((err) => setError(err.message))
    }
  }
  const cerrar = () => { setPanel(null); setError(''); setErrores({}) }
  const abierto = (tipo, cliente) => panel?.tipo === tipo && panel.id === (cliente?.id ?? null)
  const reemplazar = (c) => setClientes((lista) => lista.map((x) => (x.id === c.id ? c : x)))

  // Envía algo a la API mostrando «Guardando…» y los errores en su lugar
  const enviar = async (accion) => {
    setEnviando(true)
    setError('')
    setErrores({})
    try {
      await accion()
    } catch (err) {
      if (err.status === 400 && err.datos && !err.datos.detail) setErrores(err.datos)
      else setError(err.message)
    } finally {
      setEnviando(false)
    }
  }

  const guardarCliente = (e) => {
    e.preventDefault()
    const limite = leerNumero(form.limite)
    if (form.limite.trim() && (limite === null || limite < 0)) return setErrores({ limite: 'Escribí el límite con números, o dejalo vacío.' })
    const datos = { nombre: form.nombre, dni: form.dni, telefono: form.telefono, direccion: form.direccion, nota: form.nota }
    if (esDueño) datos.limite = form.limite.trim() ? limite.toFixed(2) : null
    enviar(async () => {
      if (panel.tipo === 'nuevo') {
        const c = await api('/api/clientes/', { metodo: 'POST', datos })
        setClientes((lista) => [...lista, c].sort((a, b) => a.nombre.localeCompare(b.nombre)))
        setAviso(`${c.nombre} ya está cargado. Para fiarle, en Vender elegí «Cuenta corriente».`)
      } else {
        const c = await api(`/api/clientes/${panel.id}/`, { metodo: 'PATCH', datos })
        reemplazar(c)
        setAviso(`Se guardaron los datos de ${c.nombre}.`)
      }
      setPanel(null)
    })
  }

  const cobrarPago = (e, cliente) => {
    e.preventDefault()
    const importe = leerNumero(pago.importe)
    if (importe === null || importe <= 0) return setError('Escribí cuánto paga, con números.')
    if (importe > Number(cliente.saldo)) return setError(`${cliente.nombre} debe ${pesos(cliente.saldo)}: no se puede cobrar más que eso.`)
    enviar(async () => {
      const r = await api(`/api/clientes/${cliente.id}/pago/`, { metodo: 'POST', datos: { importe: importe.toFixed(2), medio_pago: pago.medio } })
      const { comprobante: c, ...actualizado } = r
      reemplazar(actualizado)
      setPanel(null)
      setComprobante(c)
    })
  }

  const ajustar = (e, cliente) => {
    e.preventDefault()
    const importe = leerNumero(ajuste.importe)
    if (importe === null || importe <= 0) return setError('Escribí el importe del ajuste, con números.')
    if (!ajuste.motivo.trim()) return setError('Indicá el motivo del ajuste.')
    enviar(async () => {
      const r = await api(`/api/clientes/${cliente.id}/ajuste/`, {
        metodo: 'POST', datos: { importe: (ajuste.suma ? importe : -importe).toFixed(2), motivo: ajuste.motivo },
      })
      const { comprobante: movimiento, ...actualizado } = r
      reemplazar(actualizado)
      setMovimientos((lista) => [movimiento, ...(lista ?? [])])
      setAjuste({ suma: true, importe: '', motivo: '' })
      setAviso(`Cuenta de ${cliente.nombre} ajustada: ${textoSaldo(actualizado.saldo).toLowerCase()}.`)
    })
  }

  const guardarLimiteGeneral = (e) => {
    e.preventDefault()
    const n = leerNumero(textoLimite)
    if (textoLimite.trim() && (n === null || n < 0)) return setError('Escribí el límite con números, o dejalo vacío para que no haya límite.')
    enviar(async () => {
      await api('/api/cuentas/configuracion/', { metodo: 'POST', datos: { limite_general: textoLimite.trim() ? n.toFixed(2) : null } })
      await cargar() // cambia lo que le queda a cada cliente
      setPanel(null)
      setAviso(textoLimite.trim() ? `El límite general de fiado ahora es ${pesos(n)}.` : 'Ya no hay límite general de fiado.')
    })
  }

  const cambiarEstado = (cliente, ruta, datos, mensaje) =>
    enviar(async () => {
      reemplazar(await api(`/api/clientes/${cliente.id}/${ruta}/`, { metodo: 'POST', datos }))
      setPanel(null)
      setAviso(mensaje)
    })

  // ---------- Después de cobrar un pago: el comprobante ----------
  if (comprobante) {
    return (
      <>
        <Encabezado />
        <main className="contenedor venta-cobrada">
          <div className="monto-rosa no-imprimir" role="status">
            <span>Pago cobrado · {comprobante.medio_pago_texto}</span>
            <b>{pesos(-Number(comprobante.importe))}</b>
            <span>{comprobante.cliente_nombre}: {textoSaldo(comprobante.saldo_resultante).toLowerCase()}</span>
          </div>
          <Comprobante movimiento={comprobante} config={config} />
          <div className="botones no-imprimir">
            <button autoFocus onClick={() => setComprobante(null)}>Volver a las cuentas</button>
            <button className="boton-borde" onClick={() => imprimirRecibo(config.ancho)}>Imprimir comprobante</button>
          </div>
        </main>
      </>
    )
  }

  const texto = busqueda.trim().toLowerCase()
  const activos = clientes.filter((c) => c.activo)
  const visibles = clientes.filter(
    (c) =>
      c.activo === verActivos &&
      (!soloDeudores || Number(c.saldo) > 0) &&
      (!texto || c.nombre.toLowerCase().includes(texto) || c.dni === busqueda.trim()),
  )
  const deudores = clientes.filter((c) => Number(c.saldo) > 0)
  const deudaTotal = deudores.reduce((suma, c) => suma + Number(c.saldo), 0)
  const errorDe = (campo) => errores[campo] && <span className="error-campo">{[errores[campo]].flat().join(' ')}</span>
  const campo = (nombre, titulo, extra = {}) => (
    <label>
      {titulo}
      <input value={form[nombre]} autoComplete="off" onChange={(e) => setForm({ ...form, [nombre]: e.target.value })} {...extra} />
      {errorDe(nombre)}
    </label>
  )

  const formularioCliente = (
    <form className="tarjeta panel-cuenta" onSubmit={guardarCliente} noValidate>
      <strong>{panel?.tipo === 'nuevo' ? 'Nuevo cliente' : 'Corregir los datos'}</strong>
      <div className="fila-precios">
        {campo('nombre', 'Nombre y apellido', { maxLength: 100, autoFocus: true, required: true })}
        {campo('dni', <>DNI o CUIT <small>(opcional)</small></>, { maxLength: 13, inputMode: 'numeric' })}
        {campo('telefono', <>Teléfono <small>(opcional)</small></>, { maxLength: 30 })}
        {campo('direccion', <>Dirección <small>(opcional)</small></>, { maxLength: 150 })}
        {campo('nota', <>Nota <small>(opcional)</small></>, { maxLength: 200, placeholder: 'Ej.: paga los viernes' })}
        {esDueño && campo('limite', <>Límite propio de fiado <small>(vacío = usa el general)</small></>, {
          inputMode: 'decimal', placeholder: limiteGeneral != null ? `General: ${pesos(limiteGeneral)}` : 'General: sin límite',
        })}
      </div>
      {!esDueño && <small className="texto-suave">El límite de fiado lo fijan los dueños.</small>}
      <div className="botones">
        <button type="submit" disabled={enviando}>{enviando ? 'Guardando…' : 'Guardar'}</button>
        <button type="button" className="boton-secundario" onClick={cerrar}>Cancelar</button>
      </div>
    </form>
  )

  return (
    <>
      <Encabezado />
      <main className="contenedor">
        <div className="titulo-con-accion">
          <div>
            <h1>Cuentas corrientes</h1>
            <p className="subtitulo">Clientes que compran fiado: cuánto deben y sus pagos</p>
          </div>
          {gestiona && <button className="boton" onClick={() => abrir('nuevo')}>+ Nuevo cliente</button>}
        </div>

        <div className="tarjeta vendido-hoy">
          <div>
            <small className="texto-suave">Deben en total</small>
            <b className={deudaTotal > 0 ? 'texto-rojo' : ''}>{pesos(deudaTotal)}</b>
            <small className="texto-suave">{deudores.length} {deudores.length === 1 ? 'cliente con deuda' : 'clientes con deuda'}</small>
          </div>
          <div>
            <small className="texto-suave">Límite general de fiado</small>
            <span>{limiteGeneral != null ? pesos(limiteGeneral) : 'Sin límite'}</span>
            {esDueño
              ? <button className="boton-texto" onClick={() => abrir('limite')}>Cambiar</button>
              : <small className="texto-suave">Lo fijan los dueños</small>}
          </div>
        </div>

        {abierto('limite') && (
          <form className="tarjeta panel-cuenta" onSubmit={guardarLimiteGeneral} noValidate>
            <strong>Límite general de fiado</strong>
            <small className="texto-suave">
              Es lo máximo que puede deber cualquier cliente que no tenga un límite propio. Si una compra fiada lo pasa,
              el sistema no deja anotarla. Dejalo vacío para que no haya límite.
            </small>
            <label>
              Límite en pesos
              <input value={textoLimite} inputMode="decimal" autoComplete="off" autoFocus placeholder="Vacío = sin límite"
                onChange={(e) => setTextoLimite(e.target.value)} />
            </label>
            <div className="botones">
              <button type="submit" disabled={enviando}>{enviando ? 'Guardando…' : 'Guardar'}</button>
              <button type="button" className="boton-secundario" onClick={cerrar}>Cancelar</button>
            </div>
          </form>
        )}

        {abierto('nuevo') && formularioCliente}

        <div className="pestanas" role="tablist">
          <button role="tab" aria-selected={verActivos} onClick={() => setVerActivos(true)}>Activos ({activos.length})</button>
          <button role="tab" aria-selected={!verActivos} onClick={() => setVerActivos(false)}>
            Dados de baja ({clientes.length - activos.length})
          </button>
          <button role="tab" aria-selected={soloDeudores} onClick={() => setSoloDeudores(!soloDeudores)}>Solo los que deben</button>
        </div>

        <input type="search" className="buscador" placeholder="Buscar por nombre o DNI" value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)} />

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
            {texto || soloDeudores
              ? 'Ningún cliente coincide.'
              : verActivos
                ? gestiona
                  ? 'Todavía no hay clientes. Usá «+ Nuevo cliente».'
                  : 'Todavía no hay clientes. Los cargan los dueños o un encargado autorizado.'
                : 'No hay clientes dados de baja.'}
          </p>
        ) : (
          <ul className="lista-usuarios">
            {visibles.map((c) => {
              const saldo = Number(c.saldo)
              return (
                <li key={c.id} className={`tarjeta fila-usuario ${saldo > 0 ? 'borde-rojo' : 'borde-verde'}`}>
                  <div className="datos-usuario">
                    <strong>{c.nombre}</strong>
                    <span className="texto-suave">
                      {[c.dni && `DNI ${c.dni}`, c.telefono && `Tel. ${c.telefono}`, c.direccion].filter(Boolean).join(' · ') || 'Sin datos de contacto'}
                    </span>
                    {c.nota && <small className="texto-suave">{c.nota}</small>}
                    <small className="texto-suave">
                      {c.limite_vigente == null
                        ? 'Sin límite de fiado'
                        : <>Límite {pesos(c.limite_vigente)} {c.limite != null ? '(propio)' : '(general)'} · le quedan {pesos(c.disponible)}</>}
                    </small>
                  </div>

                  <div className="stock-cantidad">
                    <b className={saldo > 0 ? 'texto-rojo saldo-cliente' : 'saldo-cliente'}>{textoSaldo(saldo)}</b>
                  </div>

                  <div className="botones botones-stock">
                    {saldo > 0 && <button className="boton-chico" onClick={() => abrir('pago', c)}>Cobrar pago</button>}
                    <button className="boton-chico boton-borde" onClick={() => abrir('cuenta', c)}>Ver la cuenta</button>
                    {gestiona && <button className="boton-chico boton-borde" onClick={() => abrir('editar', c)}>Editar</button>}
                    {gestiona && (c.activo
                      ? <button className="boton-chico boton-texto" onClick={() => abrir('baja', c)}>Dar de baja</button>
                      : <button className="boton-chico boton-borde" disabled={enviando}
                          onClick={() => cambiarEstado(c, 'reactivar', undefined, `${c.nombre} volvió a estar activo.`)}>Reactivar</button>)}
                  </div>

                  {abierto('pago', c) && (
                    <form className="panel-stock" onSubmit={(e) => cobrarPago(e, c)} noValidate>
                      <strong>Cobrar un pago de {c.nombre}</strong>
                      <label>
                        ¿Cuánto paga? <small>(debe {pesos(c.saldo)}; puede pagar una parte)</small>
                        <input value={pago.importe} inputMode="decimal" autoComplete="off" autoFocus
                          onFocus={(e) => e.target.select()} onChange={(e) => setPago({ ...pago, importe: e.target.value })} />
                      </label>
                      <fieldset className="grupo">
                        <legend>¿Cómo paga?</legend>
                        <div className="opciones-fila">
                          {MEDIOS.map(([valor, nombre]) => (
                            <button type="button" key={valor} className={`opcion-boton opcion-chica ${pago.medio === valor ? 'elegida' : ''}`}
                              aria-pressed={pago.medio === valor} onClick={() => setPago({ ...pago, medio: valor })}>
                              {nombre}
                            </button>
                          ))}
                        </div>
                      </fieldset>
                      <div className="botones">
                        <button type="submit" disabled={enviando}>{enviando ? 'Guardando…' : 'Cobrar el pago'}</button>
                        <button type="button" className="boton-secundario" onClick={cerrar}>Cancelar</button>
                      </div>
                    </form>
                  )}

                  {abierto('editar', c) && formularioCliente}

                  {abierto('baja', c) && (
                    <ConfirmarBaja
                      mensaje={<>¿Dar de baja a <b>{c.nombre}</b>? No se le va a poder fiar más.{saldo > 0 && <> Su deuda de {pesos(saldo)} no se borra: se puede seguir cobrando.</>} Se puede reactivar.</>}
                      onConfirmar={(motivo) => cambiarEstado(c, 'desactivar', { motivo }, `${c.nombre} fue dado de baja.`)}
                      onCancelar={cerrar}
                    />
                  )}

                  {abierto('cuenta', c) && (
                    <div className="panel-stock">
                      <div className="titulo-con-accion">
                        <strong>Cuenta de {c.nombre}</strong>
                        <button className="boton-texto" onClick={cerrar}>Cerrar</button>
                      </div>
                      {movimientos === null ? (
                        <span className="texto-suave">Cargando…</span>
                      ) : movimientos.length === 0 ? (
                        <span className="texto-suave">Todavía no tiene movimientos.</span>
                      ) : (
                        <div className="tabla-con-scroll">
                          <table>
                            <thead>
                              <tr><th>Fecha</th><th>Qué pasó</th><th className="numero">Importe</th><th className="numero">Quedó</th><th>Quién</th></tr>
                            </thead>
                            <tbody>
                              {movimientos.map((m) => (
                                <tr key={m.id}>
                                  <td>{fechaHora(m.fecha_hora)}</td>
                                  <td>
                                    {m.tipo_texto}
                                    <small className="texto-suave">
                                      {m.tipo === 'PAGO' ? ` · ${m.medio_pago_texto}` : m.venta_numero ? ` · recibo N° ${m.venta_numero}` : ''}
                                      {m.detalle && m.tipo !== 'COMPRA' ? ` · ${m.detalle}` : ''}
                                    </small>
                                  </td>
                                  <td className={`numero ${Number(m.importe) < 0 ? 'texto-verde' : ''}`}>{conSigno(m.importe)}</td>
                                  <td className="numero">{textoSaldo(m.saldo_resultante)}</td>
                                  <td>{m.usuario}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}

                      {esDueño && (
                        <form className="ajuste-cuenta" onSubmit={(e) => ajustar(e, c)} noValidate>
                          <strong>Ajustar la cuenta a mano</strong>
                          <small className="texto-suave">
                            Para cargar lo que ya debía en el cuaderno o corregir un error. Queda registrado a tu nombre.
                          </small>
                          <div className="fila-precios">
                            <div className="opciones-fila">
                              <button type="button" className={`opcion-boton ${ajuste.suma ? 'elegida' : ''}`} aria-pressed={ajuste.suma}
                                onClick={() => setAjuste({ ...ajuste, suma: true })}>Sumar deuda</button>
                              <button type="button" className={`opcion-boton ${!ajuste.suma ? 'elegida' : ''}`} aria-pressed={!ajuste.suma}
                                onClick={() => setAjuste({ ...ajuste, suma: false })}>Restar deuda</button>
                            </div>
                            <label>
                              Importe
                              <input value={ajuste.importe} inputMode="decimal" autoComplete="off"
                                onChange={(e) => setAjuste({ ...ajuste, importe: e.target.value })} />
                            </label>
                            <label>
                              Motivo
                              <input value={ajuste.motivo} maxLength={200} placeholder="Ej.: deuda del cuaderno"
                                onChange={(e) => setAjuste({ ...ajuste, motivo: e.target.value })} />
                            </label>
                          </div>
                          <button type="submit" className="boton-borde" disabled={enviando}>{enviando ? 'Guardando…' : 'Guardar el ajuste'}</button>
                        </form>
                      )}
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </main>
    </>
  )
}
