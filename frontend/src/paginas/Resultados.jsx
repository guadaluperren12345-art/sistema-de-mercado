import { useState } from 'react'
import { Link } from 'react-router-dom'
import Encabezado from '../componentes/Encabezado'
import SelectorPeriodo from '../componentes/SelectorPeriodo'
import { cantidad, pesos } from '../formato'
import { hoy, parametrosDe } from '../periodo'
import { useConsulta } from '../useConsulta'

// Resultados por sección (RF-51 a RF-54). Solo dueños.
// Cada sección (Almacén, Carnicería, Verdulería) muestra lo que vendió, lo que costó esa mercadería
// y lo que se perdió, con el detalle de sus productos. Los gastos no tienen sección: se restan una sola
// vez, en el resultado del mercado entero.

const TIPOS = [['dia', 'Día'], ['semana', 'Semana'], ['mes', 'Mes'], ['anio', 'Año']]

const numero = (texto) => Number(texto)
// Plata con signo: «−$ 1.500,00» si es negativa
const dinero = (valor) => (numero(valor) < 0 ? `−${pesos(-numero(valor))}` : pesos(valor))
const color = (valor) => (numero(valor) < 0 ? 'texto-rojo' : numero(valor) > 0 ? 'texto-verde' : '')
const veredicto = (valor) => (numero(valor) < 0 ? 'Pérdida' : numero(valor) > 0 ? 'Ganancia' : 'Sin movimientos')

export default function Resultados() {
  const [tipo, setTipo] = useState('mes')
  const [ancla, setAncla] = useState(hoy())
  const [abiertas, setAbiertas] = useState([]) // secciones con el detalle de productos a la vista
  const { datos, error } = useConsulta(`/api/resultados/?${parametrosDe(tipo, ancla)}`)

  const alternar = (id) => setAbiertas((lista) => (lista.includes(id) ? lista.filter((x) => x !== id) : [...lista, id]))
  const g = datos?.general
  const c = datos?.comparacion

  return (
    <>
      <Encabezado />
      <main className="contenedor">
        <h1>Resultados por sección</h1>
        <p className="subtitulo">Cuánto ganó o perdió cada sección, con sus productos, y el mercado entero</p>

        <SelectorPeriodo tipo={tipo} ancla={ancla} tipos={TIPOS} onCambiar={(t, a) => { setTipo(t); setAncla(a) }} />

        {error ? (
          <p className="mensaje-error" role="alert">{error}</p>
        ) : datos === null ? (
          <p className="subtitulo">Cargando…</p>
        ) : (
          <>
            {/* El mercado entero: la suma de las secciones menos los gastos */}
            <section className="tarjeta cuenta-final" aria-label="Resultado general">
              {datos.secciones.map((s) => (
                <div key={s.id} className="recibo-fila">
                  <span>{s.seccion}</span>
                  <b className={color(s.resultado)}>{dinero(s.resultado)}</b>
                </div>
              ))}
              <div className="recibo-fila">
                <span><b>Suma de las tres secciones</b></span>
                <b>{dinero(g.resultado_secciones)}</b>
              </div>
              <div className="recibo-fila">
                <span>Gastos del mercado <small className="texto-suave">(no se reparten por sección) · <Link to="/gastos">ver la lista</Link></small></span>
                <b className={numero(g.gastos) > 0 ? 'texto-rojo' : ''}>{numero(g.gastos) > 0 ? '−' : ''}{pesos(g.gastos)}</b>
              </div>
              <div className="recibo-fila cuenta-final-total">
                <span>Resultado del mercado · {veredicto(g.resultado)}</span>
                <b className={color(g.resultado)}>{dinero(g.resultado)}</b>
              </div>
            </section>

            {(c.vende_mas || c.pierde_mas) && (
              <ul className="tarjetas-totales">
                <li className="tarjeta">
                  <small>La que más vende</small>
                  <b>{c.vende_mas ?? '—'}</b>
                </li>
                <li className="tarjeta">
                  <small>La que más gana</small>
                  <b className="texto-verde">{c.gana_mas ?? '—'}</b>
                </li>
                <li className="tarjeta">
                  <small>La que más pérdidas tiene</small>
                  <b className={c.pierde_mas ? 'texto-rojo' : ''}>{c.pierde_mas ?? '—'}</b>
                </li>
              </ul>
            )}

            {datos.secciones.map((s) => {
              const abierta = abiertas.includes(s.id)
              return (
                <section key={s.id} className={`tarjeta seccion-resultado borde-${numero(s.resultado) < 0 ? 'rojo' : numero(s.resultado) > 0 ? 'verde' : 'gris'}`}>
                  <div className="titulo-con-accion">
                    <div>
                      <h2>{s.seccion}</h2>
                      <small className="texto-suave">{veredicto(s.resultado)}</small>
                    </div>
                    <b className={`resultado-seccion ${color(s.resultado)}`}>{dinero(s.resultado)}</b>
                  </div>

                  <div className="cuentas-seccion">
                    <div><small className="texto-suave">Vendió</small><span>{pesos(s.ventas)}</span></div>
                    <div><small className="texto-suave">Costó esa mercadería</small><span>−{pesos(s.costo)}</span></div>
                    <div><small className="texto-suave">Pérdidas de mercadería</small><span className={numero(s.perdidas) > 0 ? 'texto-rojo' : ''}>−{pesos(s.perdidas)}</span></div>
                  </div>

                  {s.productos.length === 0 ? (
                    <small className="texto-suave">Ningún producto de esta sección tuvo ventas ni pérdidas en este período.</small>
                  ) : (
                    <>
                      <button className="boton-borde boton-chico" aria-expanded={abierta} onClick={() => alternar(s.id)}>
                        {abierta ? 'Ocultar los productos' : `Ver los ${s.productos.length === 1 ? 'productos (1)' : `${s.productos.length} productos`} de ${s.seccion}`}
                      </button>
                      {abierta && (
                        <div className="tabla-con-scroll">
                          <table>
                            <thead>
                              <tr>
                                <th>Producto</th><th className="numero">Se vendió</th><th className="numero">Vendido</th>
                                <th className="numero">Costo</th><th className="numero">Pérdidas</th><th className="numero">Resultado</th>
                              </tr>
                            </thead>
                            <tbody>
                              {s.productos.map((p) => (
                                <tr key={p.id}>
                                  <td>{p.nombre} <small className="texto-suave">{p.categoria}</small></td>
                                  <td className="numero">{numero(p.vendido) ? cantidad(p.vendido, p.unidad) : '—'}</td>
                                  <td className="numero">{pesos(p.ventas)}</td>
                                  <td className="numero">{pesos(p.costo)}</td>
                                  <td className={`numero ${numero(p.perdidas) > 0 ? 'texto-rojo' : ''}`}>
                                    {numero(p.perdidas) > 0 ? <>{pesos(p.perdidas)} <small>({cantidad(p.perdido, p.unidad)})</small></> : '—'}
                                  </td>
                                  <td className={`numero ${color(p.resultado)}`}><b>{dinero(p.resultado)}</b></td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </>
                  )}
                </section>
              )
            })}

            <p className="subtitulo nota-precios">
              El resultado de una sección es lo que vendió, menos lo que costó esa mercadería, menos lo que se perdió (vencido,
              roto o en mal estado). Cada producto cuenta en la sección donde está cargado hoy. No incluye las diferencias de
              recuento ni lo pagado a comerciantes: eso está en «Resumen y cierre del día».
            </p>
          </>
        )}
      </main>
    </>
  )
}
