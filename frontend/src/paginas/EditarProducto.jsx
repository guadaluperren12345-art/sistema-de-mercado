import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import Encabezado from '../componentes/Encabezado'
import CampoPresentacion from '../componentes/CampoPresentacion'
import SelectorCategoria from '../componentes/SelectorCategoria'
import { leerNumero, pesos, porUnidad } from '../formato'

// Corrección de un producto: nombre, número, código de barras, categoría y unidad. Dueños y encargados.
// Los precios no se cambian acá (módulo de precios, etapa 6).

export default function EditarProducto() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [producto, setProducto] = useState(null)
  const [secciones, setSecciones] = useState([])
  const [seccionId, setSeccionId] = useState(null)
  const [categoria, setCategoria] = useState('')
  const [nombre, setNombre] = useState('')
  const [codigo, setCodigo] = useState('')
  const [codigoBarras, setCodigoBarras] = useState('')
  const [unidad, setUnidad] = useState('UNIDAD')
  const [presentacion, setPresentacion] = useState('SUELTO')
  const [contenido, setContenido] = useState('')
  const [errores, setErrores] = useState({})
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)

  useEffect(() => {
    Promise.all([api(`/api/productos/${id}/`), api('/api/secciones/')])
      .then(([p, s]) => {
        setProducto(p)
        setSecciones(s)
        setSeccionId(p.seccion_id)
        setCategoria(String(p.categoria))
        setNombre(p.nombre)
        setCodigo(p.codigo ?? '')
        setCodigoBarras(p.codigo_barras ?? '')
        setUnidad(p.unidad)
        setPresentacion(p.presentacion)
        setContenido(p.contenido ? String(Number(p.contenido)).replace('.', ',') : '')
      })
      .catch((err) => setError(err.status === 404 ? 'El producto no existe.' : err.message))
  }, [id])

  const seccion = secciones.find((s) => s.id === seccionId)

  const elegirSeccion = (s) => {
    if (s.id === seccionId) return
    setSeccionId(s.id)
    setCategoria('') // la categoría es de cada sección: hay que elegir una de la nueva
  }

  const agregarCategoria = (nueva) => {
    setSecciones((lista) =>
      lista.map((s) => (s.id === nueva.seccion ? { ...s, categorias: [...s.categorias, nueva] } : s)),
    )
    setCategoria(String(nueva.id))
  }

  const limpiarError = (campo) => setErrores((e) => ({ ...e, [campo]: undefined }))

  const enviar = async (e) => {
    e.preventDefault()
    setError('')
    const errs = {}
    if (!categoria) errs.categoria = 'Elegí una categoría.'
    if (!nombre.trim()) errs.nombre = 'Escribí el nombre del producto.'
    const nContenido = leerNumero(contenido)
    if (presentacion !== 'SUELTO' && (nContenido === null || nContenido <= 0)) errs.contenido = 'Escribí cuánto trae cada una.'
    else if (presentacion !== 'SUELTO' && unidad === 'UNIDAD' && !Number.isInteger(nContenido)) errs.contenido = 'Va por unidad: tiene que ser un número entero.'
    setErrores(errs)
    if (Object.keys(errs).length) return

    setEnviando(true)
    try {
      const p = await api(`/api/productos/${id}/`, {
        metodo: 'PATCH',
        datos: {
          nombre, codigo, codigo_barras: codigoBarras, categoria: Number(categoria), unidad,
          presentacion, contenido: presentacion === 'SUELTO' ? null : String(nContenido),
        },
      })
      navigate('/productos', { replace: true, state: { aviso: `Se guardaron los cambios de «${p.nombre}».` } })
    } catch (err) {
      if (err.status === 400 && err.datos && !err.datos.detail) setErrores(err.datos)
      else setError(err.message)
      setEnviando(false)
    }
  }

  const errorDe = (campo) =>
    errores[campo] && <span className="error-campo">{[errores[campo]].flat().join(' ')}</span>

  if (!producto) {
    return (
      <>
        <Encabezado />
        <main className="contenedor">
          {error ? <p className="mensaje-error" role="alert">{error}</p> : <p className="subtitulo">Cargando…</p>}
          <Link to="/productos">Volver a la lista</Link>
        </main>
      </>
    )
  }

  return (
    <>
      <Encabezado />
      <main className="pantalla-centrada sin-alto">
        <form className="tarjeta formulario formulario-ancho" onSubmit={enviar} noValidate>
          <h1>Editar producto</h1>
          <p className="subtitulo">Corregí los datos que estén mal cargados</p>
          {!producto.activo && <p className="aviso">Este producto está dado de baja.</p>}

          <label>
            Nombre del producto
            <input value={nombre} maxLength={100} required autoFocus
              onChange={(e) => { setNombre(e.target.value); limpiarError('nombre') }} />
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
            <legend>Sección</legend>
            <div className="opciones-fila">
              {secciones.map((s) => (
                <button type="button" key={s.id} className={`opcion-boton ${s.id === seccionId ? 'elegida' : ''}`}
                  aria-pressed={s.id === seccionId} onClick={() => elegirSeccion(s)}>
                  {s.nombre}
                </button>
              ))}
            </div>
          </fieldset>

          {seccion && (
            <SelectorCategoria
              seccion={seccion}
              valor={categoria}
              onCambiar={(v) => { setCategoria(v); limpiarError('categoria') }}
              onNueva={agregarCategoria}
              error={errorDe('categoria')}
            />
          )}

          <fieldset className="grupo">
            <legend>Se vende</legend>
            <div className="opciones-fila">
              {[['UNIDAD', 'Por unidad'], ['KG', 'Por kilo']].map(([valor, texto]) => (
                <button type="button" key={valor} className={`opcion-boton ${unidad === valor ? 'elegida' : ''}`}
                  aria-pressed={unidad === valor} onClick={() => setUnidad(valor)}>
                  {texto}
                </button>
              ))}
            </div>
          </fieldset>

          <CampoPresentacion
            presentacion={presentacion}
            contenido={contenido}
            unidad={unidad}
            onPresentacion={(v) => { setPresentacion(v); limpiarError('contenido') }}
            onContenido={(v) => { setContenido(v); limpiarError('contenido') }}
            error={errorDe('contenido')}
          />

          <div className="precios-fijos">
            <span>Precio de venta: <b>{pesos(producto.precio_venta)}</b> {porUnidad(producto)}</span>
            {'precio_costo' in producto && <span>Costo: <b>{pesos(producto.precio_costo)}</b> {porUnidad(producto)}</span>}
            <small className="texto-suave">Los precios se cambian desde <Link to="/precios">Precios</Link>.</small>
          </div>

          {error && <p className="mensaje-error" role="alert">{error}</p>}

          <button type="submit" disabled={enviando}>{enviando ? 'Guardando…' : 'Guardar cambios'}</button>
          <Link to="/productos" className="boton boton-secundario">Cancelar</Link>
        </form>
      </main>
    </>
  )
}
