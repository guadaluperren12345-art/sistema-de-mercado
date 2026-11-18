import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth/AuthContext'
import Encabezado from '../componentes/Encabezado'
import { pesos } from '../formato'

// Módulos del sistema y qué roles los ven (matriz de permisos 4.3).
// Los que no tienen `ruta` todavía no están hechos y figuran como "Próximamente".
const MODULOS = [
  { nombre: 'Vender', roles: ['Administrador', 'Encargado', 'Empleado'], ruta: '/ventas', detalle: 'Escanear productos y cobrar' },
  { nombre: 'Recibos', roles: ['Administrador', 'Encargado', 'Empleado'], ruta: '/recibos', detalle: 'Los de hoy y de la semana' },
  { nombre: 'Cuentas corrientes', roles: ['Administrador', 'Encargado', 'Empleado'], ruta: '/clientes', detalle: 'Fiado: deudas y pagos de clientes' },
  { nombre: 'Stock', roles: ['Administrador', 'Encargado', 'Empleado'], ruta: '/stock', detalle: 'Cuánto hay de cada producto' },
  { nombre: 'Productos', roles: ['Administrador', 'Encargado'], ruta: '/productos', detalle: 'Altas y bajas por sección' },
  { nombre: 'Compras a comerciantes', roles: ['Administrador', 'Encargado'], ruta: '/compras', detalle: 'Qué se compró, a quién y si está pago' },
  { nombre: 'Gastos', roles: ['Administrador', 'Encargado', 'Empleado'], ruta: '/gastos', detalle: 'Anotar un monto y para qué fue' },
  { nombre: 'Precios', roles: ['Administrador', 'Encargado'], ruta: '/precios', detalle: 'Subir o bajar por categoría' },
  { nombre: 'Mensajes al dueño', roles: ['Encargado'] },
  { nombre: 'Resumen y cierre del día', roles: ['Administrador'], ruta: '/resumen', detalle: 'Entradas, salidas y cierre de las 00:45' },
  { nombre: 'Avisos', roles: ['Administrador'], ruta: '/avisos', detalle: 'La caja del día: acá, por Telegram y por correo' },
  { nombre: 'Horarios del personal', roles: ['Administrador'], ruta: '/horarios', detalle: 'Quién trabaja ahora y horas trabajadas' },
  { nombre: 'Actividad del sistema', roles: ['Administrador'], ruta: '/actividad', detalle: 'Quién hizo qué y a qué hora' },
  { nombre: 'Resultados por sección', roles: ['Administrador'], ruta: '/resultados', detalle: 'Cuánto gana o pierde cada sección' },
  { nombre: 'Usuarios', roles: ['Administrador'], ruta: '/usuarios', detalle: 'Altas y bajas del personal' },
  { nombre: 'Lector e impresora', roles: ['Administrador', 'Encargado', 'Empleado'], ruta: '/dispositivos', detalle: 'Conectar y probar los aparatos' },
]

const plural = (n, uno, varios) => `${n} ${n === 1 ? uno : varios}`

export default function Inicio() {
  const { usuario } = useAuth()
  const modulos = MODULOS.filter((m) => m.roles.includes(usuario.rol))
  const esDueño = usuario.rol === 'Administrador'
  const [stock, setStock] = useState(null) // { rojos, amarillos }
  const [porRevisar, setPorRevisar] = useState(0)
  const [avisos, setAvisos] = useState(0) // avisos sin leer (la caja del día), solo dueños
  const [vendido, setVendido] = useState(null) // lo vendido hoy (dueños y encargados, RF-41)
  const veVentas = usuario.rol !== 'Empleado'

  // Avisos: productos sin stock (todos) y horarios por revisar (dueños)
  useEffect(() => {
    api('/api/productos/?activo=1')
      .then((productos) => setStock({
        rojos: productos.filter((p) => p.semaforo === 'ROJO').length,
        amarillos: productos.filter((p) => p.semaforo === 'AMARILLO').length,
      }))
      .catch(() => {})
    if (esDueño) {
      api('/api/turnos/?estado=revisar').then((t) => setPorRevisar(t.length)).catch(() => {})
      api('/api/notificaciones/?solo=cuenta').then((n) => setAvisos(n.sin_leer)).catch(() => {})
    }
    if (veVentas) api('/api/ventas/hoy/').then(setVendido).catch(() => {})
  }, [esDueño, veVentas])

  return (
    <>
      <Encabezado />
      <main className="contenedor">
        <h1>Hola, {usuario.nombre}</h1>
        <p className="subtitulo">Elegí qué querés hacer</p>

        {vendido && (
          <div className="tarjeta vendido-hoy">
            <div>
              <small className="texto-suave">Vendido hoy</small>
              <b>{pesos(vendido.total)}</b>
              <small className="texto-suave">{plural(vendido.cantidad, 'venta', 'ventas')}</small>
            </div>
            {vendido.por_seccion.map((s) => (
              <div key={s.seccion}>
                <small className="texto-suave">{s.seccion}</small>
                <span>{pesos(s.total)}</span>
              </div>
            ))}
          </div>
        )}

        {stock && stock.rojos > 0 && (
          <Link to="/stock" className="alerta alerta-roja">
            <span className="punto punto-rojo" /> {plural(stock.rojos, 'producto sin stock', 'productos sin stock')}
            {stock.amarillos > 0 && <> · {plural(stock.amarillos, 'con poco stock', 'con poco stock')}</>} — ver
          </Link>
        )}
        {stock && stock.rojos === 0 && stock.amarillos > 0 && (
          <Link to="/stock" className="alerta alerta-amarilla">
            <span className="punto punto-amarillo" /> {plural(stock.amarillos, 'producto con poco stock', 'productos con poco stock')} — ver
          </Link>
        )}
        {avisos > 0 && (
          <Link to="/avisos" className="alerta alerta-rosa">
            {plural(avisos, 'aviso nuevo', 'avisos nuevos')}: la caja del día está hecha — ver
          </Link>
        )}
        {porRevisar > 0 && (
          <Link to="/horarios" className="alerta alerta-amarilla">
            {plural(porRevisar, 'horario para revisar', 'horarios para revisar')}: alguien se olvidó la cuenta abierta — ver
          </Link>
        )}

        <ul className="modulos">
          {modulos.map((m) =>
            m.ruta ? (
              <li key={m.nombre}>
                <Link to={m.ruta} className="tarjeta modulo">
                  <span>{m.nombre}</span>
                  <small>{m.detalle}</small>
                </Link>
              </li>
            ) : (
              <li key={m.nombre} className="tarjeta modulo deshabilitado">
                <span>{m.nombre}</span>
                <small>Próximamente</small>
              </li>
            ),
          )}
        </ul>
      </main>
    </>
  )
}
