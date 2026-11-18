import { useState } from 'react'
import { Link } from 'react-router-dom'
import Encabezado from '../componentes/Encabezado'
import SelectorPeriodo from '../componentes/SelectorPeriodo'
import { cantidad, cantidadConSigno, deFechaISO, diaCorto, duracion, hora, pesos } from '../formato'
import { hoy, parametrosDe } from '../periodo'
import { useConsulta } from '../useConsulta'

// Resumen del día, la semana o el mes: lo que entró y salió, y las horas trabajadas.
// Abajo, los cierres que el sistema hace solo cada día a las 00:45 (la caja del día). Solo dueños.

const numero = (texto) => Number(texto)
// Plata con signo: «−$ 1.500,00» si es negativa
const dinero = (valor) => (Number(valor) < 0 ? `−${pesos(-Number(valor))}` : pesos(valor))

export default function Resumen() {
  const [tipo, setTipo] = useState('dia')
  const [ancla, setAncla] = useState(hoy())
  const { datos: resumen, error } = useConsulta(`/api/resumen/?${parametrosDe(tipo, ancla)}`) // null = cargando
  const cierres = useConsulta('/api/cierres/').datos ?? []

  const m = resumen?.mercaderia
  const v = resumen?.ventas
  const g = resumen?.gastos
  const caja = resumen?.caja
  const ajuste = m ? numero(m.ajustes.valor) : 0
  const diasConDatos = resumen?.por_dia.filter(
    (d) => d.movimientos > 0 || d.minutos > 0 || numero(d.vendido) > 0 || numero(d.gastos) > 0,
  ) ?? []

  return (
    <>
      <Encabezado />
      <main className="contenedor">
        <h1>Resumen y cierre del día</h1>
        <p className="subtitulo">Lo que se vendió, lo que entró y salió, y las horas trabajadas. El sistema lo calcula solo.</p>

        <SelectorPeriodo tipo={tipo} ancla={ancla} onCambiar={(t, a) => { setTipo(t); setAncla(a) }} />

        {error ? (
          <p className="mensaje-error" role="alert">{error}</p>
        ) : resumen === null ? (
          <p className="subtitulo">Cargando…</p>
        ) : (
          <>
            {/* La cuenta final: lo que entró menos los gastos (RF-109) */}
            <section className="tarjeta cuenta-final" aria-label="Cuenta final">
              <div className="recibo-fila">
                <span>Plata que entró <small className="texto-suave">(ventas cobradas y pagos de cuentas corrientes)</small></span>
                <b className="texto-verde">{pesos(caja.entro)}</b>
              </div>
              <div className="recibo-fila">
                <span>
                  Gastos <small className="texto-suave">({g.cantidad} {g.cantidad === 1 ? 'anotado' : 'anotados'}) · <Link to="/gastos">ver la lista</Link></small>
                </span>
                <b className={numero(caja.gastos) > 0 ? 'texto-rojo' : ''}>{numero(caja.gastos) > 0 ? '−' : ''}{pesos(caja.gastos)}</b>
              </div>
              <div className="recibo-fila">
                <span>
                  Pagos a comerciantes{' '}
                  <small className="texto-suave">
                    ({resumen.comerciantes.pagos} {resumen.comerciantes.pagos === 1 ? 'pago' : 'pagos'}) · todavía se les debe{' '}
                    {pesos(resumen.comerciantes.deuda_actual)} · <Link to="/compras">ver las compras</Link>
                  </small>
                </span>
                <b className={numero(caja.pagos_comerciantes) > 0 ? 'texto-rojo' : ''}>{numero(caja.pagos_comerciantes) > 0 ? '−' : ''}{pesos(caja.pagos_comerciantes)}</b>
              </div>
              <div className="recibo-fila cuenta-final-total">
                <span>{tipo === 'dia' ? 'Cuenta final del día' : 'Cuenta final del período'}</span>
                <b className={numero(caja.resultado) < 0 ? 'texto-rojo' : ''}>{dinero(caja.resultado)}</b>
              </div>
              <div className="recibo-fila">
                <span>Efectivo que debería haber en la caja <small className="texto-suave">(efectivo que entró, menos los gastos y lo pagado en efectivo a comerciantes)</small></span>
                <b className={numero(caja.efectivo) < 0 ? 'texto-rojo' : ''}>{dinero(caja.efectivo)}</b>
              </div>
            </section>

            <ul className="tarjetas-totales">
              <li className="tarjeta">
                <small>Vendido</small>
                <b className="texto-verde">{pesos(v.total)}</b>
                <small className="texto-suave">
                  {v.cantidad} {v.cantidad === 1 ? 'venta' : 'ventas'}
                  {v.anuladas > 0 && <> · {v.anuladas} {v.anuladas === 1 ? 'anulada' : 'anuladas'}</>}
                  {v.modificadas > 0 && <> · {v.modificadas} {v.modificadas === 1 ? 'modificada' : 'modificadas'}</>}
                </small>
              </li>
              <li className="tarjeta">
                <small>Ganancia bruta</small>
                <b className={numero(v.ganancia_bruta) < 0 ? 'texto-rojo' : ''}>{pesos(v.ganancia_bruta)}</b>
                <small className="texto-suave">vendido menos el costo de esa mercadería</small>
              </li>
              <li className="tarjeta">
                <small>Ventas en efectivo</small>
                <b>{pesos(v.efectivo)}</b>
                <small className="texto-suave">sin contar pagos de cuentas ni gastos</small>
              </li>
              <li className="tarjeta">
                <small>Vendido fiado</small>
                <b>{pesos(v.fiado)}</b>
                <small className="texto-suave">en cuenta corriente · no entró plata</small>
              </li>
              <li className="tarjeta">
                <small>Pagos de cuentas corrientes</small>
                <b className="texto-verde">{pesos(resumen.cuenta_corriente.total)}</b>
                <small className="texto-suave">
                  {resumen.cuenta_corriente.cobros} {resumen.cuenta_corriente.cobros === 1 ? 'pago' : 'pagos'} · {pesos(resumen.cuenta_corriente.efectivo)} en efectivo ·{' '}
                  <Link to="/clientes">ver cuentas</Link>
                </small>
              </li>
              <li className="tarjeta">
                <small>Mercadería que entró</small>
                <b className="texto-verde">{pesos(m.ingresos.valor)}</b>
                <small className="texto-suave">{m.ingresos.movimientos} {m.ingresos.movimientos === 1 ? 'ingreso' : 'ingresos'} · al costo</small>
              </li>
              <li className="tarjeta">
                <small>Pérdidas de mercadería</small>
                <b className={numero(m.perdidas.valor) > 0 ? 'texto-rojo' : ''}>{pesos(m.perdidas.valor)}</b>
                <small className="texto-suave">{m.perdidas.movimientos} {m.perdidas.movimientos === 1 ? 'pérdida' : 'pérdidas'} · al costo</small>
              </li>
              <li className="tarjeta">
                <small>Diferencias por recuento</small>
                <b className={ajuste < 0 ? 'texto-rojo' : ''}>{ajuste > 0 ? '+' : ajuste < 0 ? '−' : ''}{pesos(Math.abs(ajuste))}</b>
                <small className="texto-suave">
                  {m.ajustes.movimientos} {m.ajustes.movimientos === 1 ? 'recuento' : 'recuentos'}
                  {ajuste < 0 ? ' · faltó mercadería' : ajuste > 0 ? ' · sobró mercadería' : ''}
                </small>
              </li>
              <li className="tarjeta">
                <small>Horas trabajadas</small>
                <b>{duracion(resumen.personal.minutos)}</b>
                <small className="texto-suave">
                  {resumen.personal.por_persona.length} {resumen.personal.por_persona.length === 1 ? 'persona' : 'personas'}
                  {resumen.personal.para_revisar > 0 && <> · <Link to="/horarios">{resumen.personal.para_revisar} para revisar</Link></>}
                </small>
              </li>
              <li className="tarjeta">
                <small>Cambios registrados</small>
                <b>{resumen.cambios}</b>
                <small className="texto-suave"><Link to="/actividad">Ver la actividad</Link></small>
              </li>
            </ul>

            <p className="aviso">
              La «ganancia bruta» es lo vendido menos el costo de esa mercadería. Los gastos y lo que se les pagó a los
              comerciantes se restan en la cuenta final de arriba, el día en que salió la plata. En este período se anotaron
              compras por {pesos(resumen.comerciantes.comprado)}. Para ver cuánto gana cada sección:{' '}
              <Link to="/resultados">Resultados por sección</Link>.
            </p>

            {g.lista.length > 0 && (
              <section className="bloque">
                <h2>Gastos</h2>
                <div className="tabla-con-scroll">
                  <table>
                    <thead>
                      <tr><th>Cuándo</th><th>Para qué</th><th>Quién lo anotó</th><th className="numero">Monto</th></tr>
                    </thead>
                    <tbody>
                      {g.lista.map((gasto) => (
                        <tr key={gasto.id}>
                          <td>{tipo === 'dia' ? hora(gasto.fecha_hora) : `${diaCorto(gasto.fecha_hora)} ${hora(gasto.fecha_hora)}`}</td>
                          <td>{gasto.proposito}</td>
                          <td>{gasto.usuario}</td>
                          <td className="numero texto-rojo">−{pesos(gasto.monto)}</td>
                        </tr>
                      ))}
                      <tr>
                        <td colSpan={3}><b>Total de gastos</b></td>
                        <td className="numero texto-rojo"><b>−{pesos(g.total)}</b></td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            {v.por_medio.length > 0 && (
              <section className="bloque">
                <h2>Ventas por medio de pago</h2>
                <div className="tabla-con-scroll">
                  <table>
                    <thead>
                      <tr><th>Medio de pago</th><th className="numero">Ventas</th><th className="numero">Total</th></tr>
                    </thead>
                    <tbody>
                      {v.por_medio.map((medio) => (
                        <tr key={medio.medio}>
                          <td>{medio.nombre}</td>
                          <td className="numero">{medio.cantidad}</td>
                          <td className="numero">{pesos(medio.total)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            {v.por_seccion.length > 0 && (
              <section className="bloque">
                <h2>Ventas por sección</h2>
                <div className="tabla-con-scroll">
                  <table>
                    <thead>
                      <tr><th>Sección</th><th className="numero">Vendido</th><th className="numero">Ganancia bruta</th></tr>
                    </thead>
                    <tbody>
                      {v.por_seccion.map((s) => (
                        <tr key={s.seccion}>
                          <td>{s.seccion}</td>
                          <td className="numero">{pesos(s.total)}</td>
                          <td className="numero">{pesos(s.ganancia_bruta)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            {m.por_seccion.length > 0 && (
              <section className="bloque">
                <h2>Mercadería por sección</h2>
                <div className="tabla-con-scroll">
                  <table>
                    <thead>
                      <tr><th>Sección</th><th className="numero">Entró</th><th className="numero">Se perdió</th></tr>
                    </thead>
                    <tbody>
                      {m.por_seccion.map((s) => (
                        <tr key={s.seccion}>
                          <td>{s.seccion}</td>
                          <td className="numero">{pesos(s.valor_ingresado)}</td>
                          <td className="numero">{pesos(s.valor_perdidas)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            {m.por_producto.length > 0 && (
              <section className="bloque">
                <h2>Mercadería por producto</h2>
                <div className="tabla-con-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Producto</th><th className="numero">Se vendió</th><th className="numero">Entró</th>
                        <th className="numero">Se perdió</th><th className="numero">Recuento</th>
                      </tr>
                    </thead>
                    <tbody>
                      {m.por_producto.map((p) => (
                        <tr key={p.id}>
                          <td>{p.nombre} <small className="texto-suave">{p.seccion}</small></td>
                          <td className="numero">{numero(p.vendido) ? cantidad(p.vendido, p.unidad) : '—'}</td>
                          <td className="numero">{numero(p.ingresado) ? cantidad(p.ingresado, p.unidad) : '—'}</td>
                          <td className="numero">{numero(p.perdido) ? cantidad(p.perdido, p.unidad) : '—'}</td>
                          <td className="numero">{numero(p.ajustado) ? cantidadConSigno(p.ajustado, p.unidad) : '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            {resumen.personal.por_persona.length > 0 && (
              <section className="bloque">
                <h2>Personal</h2>
                <div className="tabla-con-scroll">
                  <table>
                    <thead>
                      <tr><th>Persona</th><th className="numero">Ingresos al sistema</th><th className="numero">Horas</th></tr>
                    </thead>
                    <tbody>
                      {resumen.personal.por_persona.map((p) => (
                        <tr key={p.id}>
                          <td>{p.nombre} <small className="texto-suave">{p.rol}</small></td>
                          <td className="numero">{p.turnos}</td>
                          <td className="numero">{duracion(p.minutos)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            {tipo !== 'dia' && diasConDatos.length > 0 && (
              <section className="bloque">
                <h2>Día por día</h2>
                <div className="tabla-con-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Día</th><th className="numero">Vendido</th><th className="numero">Gastos</th>
                        <th className="numero">Mercadería que entró</th>
                        <th className="numero">Se perdió</th><th className="numero">Horas</th>
                      </tr>
                    </thead>
                    <tbody>
                      {diasConDatos.map((d) => (
                        <tr key={d.fecha}>
                          <td>
                            <button className="boton-texto" onClick={() => { setTipo('dia'); setAncla(deFechaISO(d.fecha)) }}>
                              {diaCorto(d.fecha)}
                            </button>
                          </td>
                          <td className="numero">{pesos(d.vendido)}</td>
                          <td className={`numero ${numero(d.gastos) > 0 ? 'texto-rojo' : ''}`}>{numero(d.gastos) > 0 ? '−' : ''}{pesos(d.gastos)}</td>
                          <td className="numero">{pesos(d.valor_ingresado)}</td>
                          <td className="numero">{pesos(d.valor_perdidas)}</td>
                          <td className="numero">{duracion(d.minutos)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            {resumen.cambios === 0 && resumen.personal.turnos === 0 && (
              <p className="subtitulo">No hubo movimientos en este período.</p>
            )}
          </>
        )}

        <section className="bloque">
          <h2>Cierres automáticos de las 00:45</h2>
          <p className="texto-suave">
            Cada noche a las 00:45 el sistema hace la caja del día, guarda los totales y te manda un aviso,
            sin que nadie tenga que hacerlo.
          </p>
          {cierres.length === 0 ? (
            <p className="texto-suave">Todavía no hay cierres: el primero se genera esta noche a las 00:45.</p>
          ) : (
            <div className="tabla-con-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Día</th><th className="numero">Vendido</th><th className="numero">Plata que entró</th>
                    <th className="numero">Gastos</th><th className="numero">Cuenta final</th>
                    <th className="numero">Efectivo en caja</th><th className="numero">Ganancia bruta</th>
                    <th className="numero">Mercadería que entró</th><th className="numero">Se perdió</th>
                    <th className="numero">Horas</th><th>Cerrado</th>
                  </tr>
                </thead>
                <tbody>
                  {cierres.map((c) => (
                    <tr key={c.id}>
                      <td>
                        <button className="boton-texto" onClick={() => { setTipo('dia'); setAncla(deFechaISO(c.fecha)); window.scrollTo(0, 0) }}>
                          {diaCorto(c.fecha)}
                        </button>
                      </td>
                      <td className="numero">{pesos(c.ventas_total)}</td>
                      <td className="numero">{pesos(c.entro)}</td>
                      <td className={`numero ${numero(c.gastos_total) > 0 ? 'texto-rojo' : ''}`}>{numero(c.gastos_total) > 0 ? '−' : ''}{pesos(c.gastos_total)}</td>
                      <td className={`numero ${numero(c.resultado_dia) < 0 ? 'texto-rojo' : ''}`}><b>{dinero(c.resultado_dia)}</b></td>
                      <td className="numero">{dinero(c.efectivo_esperado)}</td>
                      <td className="numero">{pesos(c.ganancia_bruta)}</td>
                      <td className="numero">{pesos(c.valor_ingresado)}</td>
                      <td className="numero">{pesos(c.valor_perdidas)}</td>
                      <td className="numero">
                        {duracion(c.minutos_trabajados)}
                        {c.turnos_cerrados_por_sistema > 0 && (
                          <small className="texto-suave"> · {c.turnos_cerrados_por_sistema} sin cerrar sesión</small>
                        )}
                      </td>
                      <td><small className="texto-suave">{diaCorto(c.generado_en)} {hora(c.generado_en)}</small></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </main>
    </>
  )
}
