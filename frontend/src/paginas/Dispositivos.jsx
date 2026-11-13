import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import Encabezado from '../componentes/Encabezado'
import Recibo from '../componentes/Recibo'
import { buscarPorCodigo, guardarConfig, imprimirRecibo, leerConfig, useLector } from '../dispositivos'
import { pesos, porUnidad } from '../formato'

// Conectar y probar el lector de código de barras y la impresora de recibos.
// La configuración de la impresora se guarda en este equipo (cada caja puede tener la suya).

function reciboDePrueba() {
  return {
    numero: '000000',
    fecha_hora: new Date().toISOString(),
    vendedor: 'Prueba de impresora',
    medio_pago_texto: 'Efectivo',
    total: '11125.00',
    paga_con: '12000.00',
    vuelto: '875.00',
    anulada: false,
    items: [
      { nombre: 'Agua mineral 2 L', unidad: 'UNIDAD', cantidad: '2', precio_unitario: '1500.00', subtotal: '3000.00' },
      { nombre: 'Pechuga de pollo', unidad: 'KG', cantidad: '1.250', precio_unitario: '6500.00', subtotal: '8125.00' },
    ],
  }
}

export default function Dispositivos() {
  const [productos, setProductos] = useState([])
  const [config, setConfig] = useState(leerConfig)
  const [guardado, setGuardado] = useState('')
  const [prueba] = useState(reciboDePrueba)
  const [campo, setCampo] = useState('')
  const [lectura, setLectura] = useState(null) // { codigo, producto }

  useEffect(() => {
    api('/api/productos/').then(setProductos).catch(() => {})
  }, [])

  const leido = (codigo) => {
    const c = codigo.trim()
    if (!c) return
    setLectura({ codigo: c, producto: buscarPorCodigo(productos, c) })
    setCampo('')
  }

  // Funciona con el cursor en el campo de prueba (Enter) y también fuera de él
  useLector(leido)

  const cambiar = (clave, valor) => {
    const nueva = { ...config, [clave]: valor }
    setConfig(nueva)
    setGuardado(guardarConfig(nueva) ? 'Guardado en este equipo.' : 'No se pudo guardar en este navegador.')
  }

  return (
    <>
      <Encabezado />
      <main className="contenedor">
        <div className="no-imprimir">
          <h1>Lector e impresora</h1>
          <p className="subtitulo">Conectá y probá el lector de código de barras y la impresora de recibos de esta caja</p>

          <section className="bloque tarjeta panel-dispositivo">
            <h2>Lector de código de barras</h2>
            <ol className="pasos">
              <li>Enchufá el lector por USB (o vinculalo por Bluetooth). No hay que instalar nada: funciona como un teclado.</li>
              <li>Apuntá a cualquier producto y apretá el gatillo.</li>
              <li>Acá abajo tiene que aparecer el código que leyó.</li>
            </ol>
            <input
              className="buscador"
              value={campo}
              autoFocus
              autoComplete="off"
              placeholder="Escaneá un producto (o escribí un código y apretá Enter)"
              onChange={(e) => setCampo(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') leido(campo) }}
            />

            {lectura && (
              lectura.producto ? (
                <p className="mensaje-ok" role="status">
                  El lector funciona. Leyó <b>{lectura.codigo}</b>: es <b>{lectura.producto.nombre}</b>{' '}
                  ({pesos(lectura.producto.precio_venta)} {porUnidad(lectura.producto)})
                  {!lectura.producto.activo && ' — está dado de baja'}.
                </p>
              ) : (
                <p className="aviso" role="status">
                  El lector funciona: leyó <b>{lectura.codigo}</b>, pero ningún producto tiene ese código.{' '}
                  Cargalo en <Link to="/productos">Productos</Link>, en el campo «Código de barras» (se puede escanear ahí mismo).
                </p>
              )
            )}
            <small className="texto-suave">
              Si no aparece nada: revisá que el lector esté configurado para mandar «Enter» al final de cada lectura
              (viene así de fábrica en casi todos) y que el teclado de la computadora esté en español o inglés.
            </small>
          </section>

          <section className="bloque tarjeta panel-dispositivo">
            <h2>Impresora de recibos</h2>
            <ol className="pasos">
              <li>Instalá la impresora en esta computadora como cualquier impresora de Windows (sirve una térmica de 58 u 80 mm).</li>
              <li>Completá los datos del recibo y elegí el ancho del papel.</li>
              <li>Apretá «Imprimir recibo de prueba» y, en la ventana que se abre, elegí la impresora de recibos y márgenes «Ninguno».</li>
            </ol>

            <div className="dos-columnas">
              <label>
                Nombre del negocio
                <input value={config.negocio} maxLength={40} onChange={(e) => cambiar('negocio', e.target.value)} />
              </label>
              <label>
                Dirección o teléfono <small>(opcional)</small>
                <input value={config.direccion} maxLength={60} onChange={(e) => cambiar('direccion', e.target.value)} />
              </label>
            </div>
            <label>
              Mensaje al pie <small>(opcional)</small>
              <input value={config.pie} maxLength={60} onChange={(e) => cambiar('pie', e.target.value)} />
            </label>

            <fieldset className="grupo">
              <legend>Ancho del papel</legend>
              <div className="opciones-fila">
                {[[80, '80 mm (el más común)'], [58, '58 mm (angosto)']].map(([valor, nombre]) => (
                  <button type="button" key={valor} className={`opcion-boton ${config.ancho === valor ? 'elegida' : ''}`}
                    aria-pressed={config.ancho === valor} onClick={() => cambiar('ancho', valor)}>
                    {nombre}
                  </button>
                ))}
              </div>
            </fieldset>

            <label className="opcion">
              <input type="checkbox" checked={config.imprimirSolo} onChange={(e) => cambiar('imprimirSolo', e.target.checked)} />
              <span>
                <b>Imprimir el recibo apenas se cobra</b>
                <small className="texto-suave">Si no, se imprime con el botón «Imprimir recibo» después de cada venta.</small>
              </span>
            </label>

            {guardado && <small className="texto-suave" role="status">{guardado}</small>}

            <div className="botones">
              <button onClick={() => imprimirRecibo(config.ancho)}>Imprimir recibo de prueba</button>
            </div>
            <small className="texto-suave">Así va a salir:</small>
          </section>
        </div>

        <Recibo venta={prueba} config={config} />
      </main>
    </>
  )
}
