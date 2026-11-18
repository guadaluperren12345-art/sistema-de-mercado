import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import RutaProtegida from './auth/RutaProtegida'
import Actividad from './paginas/Actividad'
import Avisos from './paginas/Avisos'
import CambiarPassword from './paginas/CambiarPassword'
import Clientes from './paginas/Clientes'
import Compras from './paginas/Compras'
import Dispositivos from './paginas/Dispositivos'
import EditarProducto from './paginas/EditarProducto'
import Gastos from './paginas/Gastos'
import Horarios from './paginas/Horarios'
import Inicio from './paginas/Inicio'
import Login from './paginas/Login'
import MovimientosStock from './paginas/MovimientosStock'
import NuevoProducto from './paginas/NuevoProducto'
import NuevoUsuario from './paginas/NuevoUsuario'
import Precios from './paginas/Precios'
import Productos from './paginas/Productos'
import Recibos from './paginas/Recibos'
import Resultados from './paginas/Resultados'
import Resumen from './paginas/Resumen'
import Stock from './paginas/Stock'
import Usuarios from './paginas/Usuarios'
import Venta from './paginas/Venta'
import './estilos.css'

const SOLO_DUEÑOS = ['Administrador']
const DUEÑOS_Y_ENCARGADOS = ['Administrador', 'Encargado']

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/cambiar-password"
            element={<RutaProtegida><CambiarPassword /></RutaProtegida>}
          />
          <Route path="/" element={<RutaProtegida><Inicio /></RutaProtegida>} />
          <Route
            path="/usuarios"
            element={<RutaProtegida roles={SOLO_DUEÑOS}><Usuarios /></RutaProtegida>}
          />
          <Route
            path="/usuarios/nuevo"
            element={<RutaProtegida roles={SOLO_DUEÑOS}><NuevoUsuario /></RutaProtegida>}
          />
          <Route
            path="/productos"
            element={<RutaProtegida roles={DUEÑOS_Y_ENCARGADOS}><Productos /></RutaProtegida>}
          />
          <Route
            path="/productos/nuevo"
            element={<RutaProtegida roles={DUEÑOS_Y_ENCARGADOS}><NuevoProducto /></RutaProtegida>}
          />
          <Route
            path="/productos/:id/editar"
            element={<RutaProtegida roles={DUEÑOS_Y_ENCARGADOS}><EditarProducto /></RutaProtegida>}
          />
          <Route
            path="/precios"
            element={<RutaProtegida roles={DUEÑOS_Y_ENCARGADOS}><Precios /></RutaProtegida>}
          />
          {/* Vender, ver recibos y probar el lector y la impresora: todos (un empleado ve solo sus recibos) */}
          <Route path="/ventas" element={<RutaProtegida><Venta /></RutaProtegida>} />
          <Route path="/recibos" element={<RutaProtegida><Recibos /></RutaProtegida>} />
          <Route path="/dispositivos" element={<RutaProtegida><Dispositivos /></RutaProtegida>} />
          {/* Cuentas corrientes: todos ven y cobran pagos; la pantalla muestra más según el rol y el permiso */}
          <Route path="/clientes" element={<RutaProtegida><Clientes /></RutaProtegida>} />
          {/* Lista de gastos: cualquiera anota; se restan en el cierre del día */}
          <Route path="/gastos" element={<RutaProtegida><Gastos /></RutaProtegida>} />
          {/* Compras a comerciantes: solo dueños y encargados */}
          <Route
            path="/compras"
            element={<RutaProtegida roles={DUEÑOS_Y_ENCARGADOS}><Compras /></RutaProtegida>}
          />
          <Route
            path="/resultados"
            element={<RutaProtegida roles={SOLO_DUEÑOS}><Resultados /></RutaProtegida>}
          />
          {/* El stock lo ven todos; los movimientos (con costos), dueños y encargados */}
          <Route path="/stock" element={<RutaProtegida><Stock /></RutaProtegida>} />
          <Route
            path="/stock/movimientos"
            element={<RutaProtegida roles={DUEÑOS_Y_ENCARGADOS}><MovimientosStock /></RutaProtegida>}
          />
          {/* Horarios, actividad y cierre del día: solo los dueños */}
          <Route
            path="/horarios"
            element={<RutaProtegida roles={SOLO_DUEÑOS}><Horarios /></RutaProtegida>}
          />
          <Route
            path="/actividad"
            element={<RutaProtegida roles={SOLO_DUEÑOS}><Actividad /></RutaProtegida>}
          />
          <Route
            path="/resumen"
            element={<RutaProtegida roles={SOLO_DUEÑOS}><Resumen /></RutaProtegida>}
          />
          {/* Avisos con la caja del día (sistema, Telegram y correo): solo los dueños */}
          <Route
            path="/avisos"
            element={<RutaProtegida roles={SOLO_DUEÑOS}><Avisos /></RutaProtegida>}
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
