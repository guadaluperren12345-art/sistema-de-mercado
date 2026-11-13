import { useState } from 'react'

// Confirmación de una baja con motivo opcional. Se usa en usuarios, productos y clientes,
// y también para anular un gasto (con `textoBoton="Sí, anular"`).
export default function ConfirmarBaja({ mensaje, onConfirmar, onCancelar, textoBoton = 'Sí, dar de baja' }) {
  const [motivo, setMotivo] = useState('')
  const [enviando, setEnviando] = useState(false)

  const confirmar = async (e) => {
    e.preventDefault()
    setEnviando(true)
    await onConfirmar(motivo)
    setEnviando(false)
  }

  return (
    <form className="confirmar-baja" onSubmit={confirmar}>
      <p>{mensaje}</p>
      <input
        placeholder="Motivo (opcional)"
        value={motivo}
        maxLength={300}
        onChange={(e) => setMotivo(e.target.value)}
        autoFocus
      />
      <div className="botones">
        <button type="submit" className="boton-peligro" disabled={enviando}>
          {enviando ? 'Guardando…' : textoBoton}
        </button>
        <button type="button" className="boton-secundario" onClick={onCancelar}>Cancelar</button>
      </div>
    </form>
  )
}
