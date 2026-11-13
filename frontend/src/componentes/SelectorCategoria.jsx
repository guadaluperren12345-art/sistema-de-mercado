import { useState } from 'react'
import { api } from '../api'

// Lista de categorías de una sección, con "+ Nueva" para crear una ahí mismo (RF-56).
export default function SelectorCategoria({ seccion, valor, onCambiar, onNueva, error }) {
  const [creando, setCreando] = useState(false)
  const [nombre, setNombre] = useState('')
  const [errorNueva, setErrorNueva] = useState('')

  const guardar = async () => {
    setErrorNueva('')
    try {
      const c = await api('/api/categorias/', { metodo: 'POST', datos: { seccion: seccion.id, nombre } })
      onNueva(c)
      setCreando(false)
      setNombre('')
    } catch (err) {
      setErrorNueva(err.message)
    }
  }

  if (creando) {
    return (
      <div className="grupo">
        <span className="etiqueta-campo">Nueva categoría en {seccion.nombre}</span>
        <div className="campo-con-boton">
          <input value={nombre} onChange={(e) => setNombre(e.target.value)} maxLength={50} autoFocus
            placeholder="Ej.: Achuras"
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); guardar() } }} />
          <button type="button" onClick={guardar} disabled={!nombre.trim()}>Agregar</button>
        </div>
        {errorNueva && <span className="error-campo">{errorNueva}</span>}
        <button type="button" className="boton-texto" onClick={() => { setCreando(false); setErrorNueva('') }}>
          Cancelar
        </button>
      </div>
    )
  }

  return (
    <label>
      Categoría
      <div className="campo-con-boton">
        <select value={valor} onChange={(e) => onCambiar(e.target.value)} required>
          <option value="">Elegí una categoría…</option>
          {seccion.categorias.map((c) => (
            <option key={c.id} value={c.id}>{c.nombre}</option>
          ))}
        </select>
        <button type="button" className="boton-secundario" onClick={() => setCreando(true)}>+ Nueva</button>
      </div>
      {error}
    </label>
  )
}
