// Lector de código de barras e impresora de recibos.
//
// Lector: los lectores USB (y la mayoría de los Bluetooth) se comportan como un teclado:
// "escriben" el código muy rápido y aprietan Enter. No hace falta instalar nada.
//
// Impresora: se usa cualquier impresora instalada en la computadora (térmica de 58 u 80 mm,
// o una común). El recibo se manda con la impresión del navegador.
//
// La configuración se guarda en ESTE dispositivo (cada caja puede tener otra impresora).

import { useEffect, useRef } from 'react'

const CLAVE = 'mercado.dispositivos'

const POR_DEFECTO = {
  negocio: 'Mercado',
  direccion: '',
  pie: '¡Gracias por su compra!',
  ancho: 80, // milímetros del papel: 80 o 58
  imprimirSolo: false, // imprimir el recibo apenas se cobra, sin apretar el botón
}

export function leerConfig() {
  try {
    return { ...POR_DEFECTO, ...JSON.parse(localStorage.getItem(CLAVE) ?? '{}') }
  } catch {
    return { ...POR_DEFECTO }
  }
}

export function guardarConfig(config) {
  try {
    localStorage.setItem(CLAVE, JSON.stringify(config))
    return true
  } catch {
    return false
  }
}

// Manda a imprimir el recibo que está en pantalla (el elemento con clase "recibo").
// Los estilos de impresión (estilos.css) ocultan todo lo demás.
export function imprimirRecibo(ancho = leerConfig().ancho) {
  const hoja = document.createElement('style')
  hoja.textContent = `@page { size: ${ancho}mm auto; margin: 0; }`
  document.head.appendChild(hoja)
  window.print()
  hoja.remove()
}

// Milisegundos máximos entre dos teclas para considerar que las escribió el lector y no una persona
const PAUSA_MAXIMA = 100
const LARGO_MINIMO = 3

// Escucha el lector cuando el cursor NO está en un campo de texto (si está en un campo,
// el lector escribe ahí y el Enter lo maneja ese campo). Llama a onCodigo("7790895000997").
export function useLector(onCodigo) {
  const destino = useRef(onCodigo)
  useEffect(() => {
    destino.current = onCodigo
  }, [onCodigo])

  useEffect(() => {
    let codigo = ''
    let ultima = 0
    const alTeclear = (e) => {
      const el = document.activeElement
      const enCampo = el && (['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName) || el.isContentEditable)
      if (enCampo || e.ctrlKey || e.altKey || e.metaKey) {
        codigo = ''
        return
      }
      const ahora = performance.now()
      if (ahora - ultima > PAUSA_MAXIMA) codigo = ''
      ultima = ahora
      if (e.key === 'Enter') {
        if (codigo.length >= LARGO_MINIMO) {
          e.preventDefault() // que el Enter del lector no apriete el botón que tenga el foco
          destino.current(codigo)
        }
        codigo = ''
      } else if (e.key.length === 1) {
        codigo += e.key
      }
    }
    window.addEventListener('keydown', alTeclear)
    return () => window.removeEventListener('keydown', alTeclear)
  }, [])
}

// Busca un producto por lo que leyó el lector o tipeó la persona: código de barras o número de producto
export function buscarPorCodigo(productos, texto) {
  const t = texto.trim()
  if (!t) return null
  return productos.find((p) => p.codigo_barras === t) ?? productos.find((p) => p.codigo === t) ?? null
}
