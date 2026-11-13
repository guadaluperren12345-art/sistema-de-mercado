// Datos del formulario rápido para crear un producto desde Stock o desde una compra (RF-122).
// El formulario está en componentes/ProductoNuevoRapido.jsx.

export const PRODUCTO_VACIO = { nombre: '', seccionId: null, categoria: '', unidad: null, venta: '', costo: '' }

// En Almacén casi todo se vende por unidad; en Carnicería y Verdulería, por kilo.
const unidadSugerida = (seccion) => (seccion?.nombre === 'Almacén' ? 'UNIDAD' : 'KG')

// La unidad elegida, o la sugerida por la sección si todavía no se tocó
export const unidadDe = (valor, secciones) => valor.unidad ?? unidadSugerida(secciones.find((s) => s.id === valor.seccionId))
