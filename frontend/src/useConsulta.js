import { useEffect, useState } from 'react'
import { api } from './api'

// Pide datos a la API cada vez que cambia la ruta (por ejemplo, al cambiar un filtro).
// Devuelve { datos, error, cargando }. Si llega tarde la respuesta de un filtro viejo, se descarta.
// `version` sirve para volver a pedir lo mismo: al cambiar el número, recarga sin mostrar "Cargando…".
export function useConsulta(ruta, version = 0) {
  const [estado, setEstado] = useState({ ruta: null, datos: null, error: '' })

  useEffect(() => {
    if (!ruta) return
    let vigente = true
    api(ruta)
      .then((datos) => vigente && setEstado({ ruta, datos, error: '' }))
      .catch((err) => vigente && setEstado({ ruta, datos: null, error: err.message }))
    return () => {
      vigente = false
    }
  }, [ruta, version])

  const actual = estado.ruta === ruta
  return {
    datos: actual ? estado.datos : null,
    error: actual ? estado.error : '',
    cargando: Boolean(ruta) && !actual,
  }
}
