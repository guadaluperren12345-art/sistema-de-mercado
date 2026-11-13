import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import Encabezado from '../componentes/Encabezado'
import CampoPresentacion from '../componentes/CampoPresentacion'
import SelectorCategoria from '../componentes/SelectorCategoria'
import { leerNumero, margen, pesos } from '../formato'

// Alta de producto (RF-31, RF-32). Dueños y encargados.
// Después de guardar, el formulario queda listo para cargar otro de la misma sección y categoría.

// En Almacén casi todo se vende por unidad; en Carnicería y Verdulería, por kilo.
const unidadSugerida = (nombreSeccion) => (nombreSeccion === 'Almacén' ? 'UNIDAD' : 'KG')

export default function NuevoProducto() {
  const [params] = useSearchParams()
  const [secciones, setSecciones] = useState([])
  const [seccionId, setSeccionId] = useState(Number(params.get('seccion')) || null)
  const [categoria, setCategoria] = useState('')
  const [nombre, setNombre] = useState('')
  const [codigo, setCodigo] = useState('')
  const [codigoBarras, setCodigoBarras] = useState('')
  const [unidad, setUnidad] = useState(null)
  const [presentacion, setPresentacion] = useState('SUELTO')
  const [contenido, setContenido] = useState('')
  const [costo, setCosto] = useState('')
  const [venta, setVenta] = useState('')
  const [errores, setErrores] = useState({})
  const [error, setError] = useState('')
  const [aviso, setAviso] = useState('')
  const [enviando, setEnviando] = useState(false)
  const nombreRef = useRef(null)

  useEffect(() => {
    api('/api/secciones/').then(setSecciones).catch((err) => setError(err.message))
  }, [])

  const seccion = secciones.find((s) => s.id === seccionId)
  const unidadElegida = unidad ?? (seccion ? unidadSugerida(seccion.nombre) : 'UNIDAD')
  const textoUnidad = unidadElegida === 'KG' ? 'por kilo' : 'por unidad'

  const elegirSeccion = (s) => {
    setSeccionId(s.id)
    setCategoria('')
    setUnidad(null)
    setErrores({})
  }

  const agregarCategoria = (nueva) => {
    setSecciones((lista) =>
      lista.map((s) => (s.id === nueva.seccion ? { ...s, categorias: [...s.categorias, nueva] } : s)),
    )
    setCategoria(String(nueva.id))
  }

  const nCosto = leerNumero(costo)
  const nVenta = leerNumero(venta)
  const m = margen(nVenta, nCosto)

  const limpiarError = (campo) => setErrores((e) => ({ ...e, [campo]: undefined }))

  const enviar = async (e) => {
    e.preventDefault()
    setError('')
    setAviso('')
    const errs = {}
    if (!seccion) errs.seccion = 'Elegí una sección.'
    if (!categoria) errs.categoria = 'Elegí una categoría.'
    if (!nombre.trim()) errs.nombre = 'Escribí el nombre del producto.'
    if (nCosto === null) errs.precio_costo = 'Escribí el costo (puede ser 0).'
    if (nVenta === null || nVenta <= 0) errs.precio_venta = 'Escribí un precio de venta mayor a 0.'
    const nContenido = leerNumero(contenido)
    if (presentacion !== 'SUELTO' && (nContenido === null || nContenido <= 0)) errs.contenido = 'Escribí cuánto trae cada una.'
    else if (presentacion !== 'SUELTO' && unidadElegida === 'UNIDAD' && !Number.isInteger(nContenido)) errs.contenido = 'Va por unidad: tiene que ser un número entero.'
    setErrores(errs)
    if (Object.keys(errs).length) return

    setEnviando(true)
    try {
      const p = await api('/api/productos/', {
        metodo: 'POST',
        datos: {
          nombre, codigo, codigo_barras: codigoBarras, categoria: Number(categoria), unidad: unidadElegida,
          presentacion, contenido: presentacion === 'SUELTO' ? null : String(nContenido),
          precio_costo: nCosto.toFixed(2), precio_venta: nVenta.toFixed(2),
        },
      })
      setAviso(`«${p.nombre}» quedó cargado en ${p.seccion} → ${p.categoria_nombre}. Podés cargar otro.`)
      setNombre('')
      setCodigo('')
      setCodigoBarras('')
      setCosto('')
      setVenta('')
      nombreRef.current?.focus()
    } catch (err) {
      if (err.status === 400 && err.datos && !err.datos.detail) setErrores(err.datos)
      else setError(err.message)
    } finally {
      setEnviando(false)
    }
  }

  const errorDe = (campo) =>
    errores[campo] && <span className="error-campo">{[errores[campo]].flat().join(' ')}</span>

  return (
    <>
      <Encabezado />
      <main className="pantalla-centrada sin-alto">
        <form className="tarjeta formulario formulario-ancho" onSubmit={enviar} noValidate>
          <h1>Nuevo producto</h1>
          <p className="subtitulo">Elegí la sección y completá los datos</p>

          {aviso && <p className="mensaje-ok" role="status">{aviso}</p>}

          <fieldset className="grupo">
            <legend>Sección</legend>
            <div className="opciones-fila">
              {secciones.map((s) => (
                <button type="button" key={s.id} className={`opcion-boton ${s.id === seccionId ? 'elegida' : ''}`}
                  aria-pressed={s.id === seccionId} onClick={() => elegirSeccion(s)}>
                  {s.nombre}
                </button>
              ))}
            </div>
            {errorDe('seccion')}
          </fieldset>

          {seccion && (
            <>
              <SelectorCategoria
                seccion={seccion}
                valor={categoria}
                onCambiar={(v) => { setCategoria(v); limpiarError('categoria') }}
                onNueva={agregarCategoria}
                error={errorDe('categoria')}
              />

              <label>
                Nombre del producto
                <input ref={nombreRef} value={nombre} maxLength={100} required
                  onChange={(e) => { setNombre(e.target.value); limpiarError('nombre') }}
                  placeholder={seccion.nombre === 'Almacén' ? 'Ej.: Fideos tirabuzón 500 g' : seccion.nombre === 'Carnicería' ? 'Ej.: Pechuga' : 'Ej.: Tomate redondo'} />
                {errorDe('nombre')}
              </label>

              <label>
                Número de producto <small>(opcional)</small>
                <input value={codigo} maxLength={30} autoComplete="off"
                  onChange={(e) => { setCodigo(e.target.value); limpiarError('codigo') }}
                  onKeyDown={(e) => { if (e.key === 'Enter') e.preventDefault() }}
                  placeholder="Uno corto propio, fácil de recordar (ej.: 101)" />
                {errorDe('codigo')}
              </label>

              <label>
                Código de barras <small>(opcional: escanealo con el lector)</small>
                <input value={codigoBarras} maxLength={30} autoComplete="off" inputMode="numeric"
                  onChange={(e) => { setCodigoBarras(e.target.value); limpiarError('codigo_barras') }}
                  // El lector escribe el código y aprieta Enter: que no guarde todavía
                  onKeyDown={(e) => { if (e.key === 'Enter') e.preventDefault() }}
                  placeholder="Ej.: 7790895000997" />
                {errorDe('codigo_barras')}
              </label>

              <fieldset className="grupo">
                <legend>Se vende</legend>
                <div className="opciones-fila">
                  {[['UNIDAD', 'Por unidad'], ['KG', 'Por kilo']].map(([valor, texto]) => (
                    <button type="button" key={valor} className={`opcion-boton ${unidadElegida === valor ? 'elegida' : ''}`}
                      aria-pressed={unidadElegida === valor} onClick={() => setUnidad(valor)}>
                      {texto}
                    </button>
                  ))}
                </div>
              </fieldset>

              <CampoPresentacion
                presentacion={presentacion}
                contenido={contenido}
                unidad={unidadElegida}
                onPresentacion={(v) => { setPresentacion(v); limpiarError('contenido') }}
                onContenido={(v) => { setContenido(v); limpiarError('contenido') }}
                error={errorDe('contenido')}
              />

              <div className="dos-columnas">
                <label>
                  Costo {textoUnidad}
                  <input value={costo} inputMode="decimal" placeholder="$ 0,00"
                    onChange={(e) => { setCosto(e.target.value); limpiarError('precio_costo') }} />
                  <small>Lo que lo pagás al comerciante</small>
                  {errorDe('precio_costo')}
                </label>
                <label>
                  Precio de venta {textoUnidad}
                  <input value={venta} inputMode="decimal" placeholder="$ 0,00"
                    onChange={(e) => { setVenta(e.target.value); limpiarError('precio_venta') }} />
                  <small>Lo que paga el cliente</small>
                  {errorDe('precio_venta')}
                </label>
              </div>

              {nVenta !== null && nCosto !== null && (
                nVenta < nCosto ? (
                  <p className="aviso">Ojo: el precio de venta es menor que el costo. Se perdería {pesos(nCosto - nVenta)} {textoUnidad}.</p>
                ) : (
                  m !== null && <p className="texto-suave">Ganancia: {pesos(nVenta - nCosto)} {textoUnidad} (margen {m.toFixed(0)}%)</p>
                )
              )}
            </>
          )}

          {error && <p className="mensaje-error" role="alert">{error}</p>}

          <button type="submit" disabled={enviando || !seccion}>{enviando ? 'Guardando…' : 'Guardar producto'}</button>
          <Link to="/productos" className="boton boton-secundario">Volver a la lista</Link>
        </form>
      </main>
    </>
  )
}
