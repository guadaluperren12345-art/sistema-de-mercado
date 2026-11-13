import { cantidad, fechaHora, pesos } from '../formato'

// Recibo de una venta, tal como sale por la impresora. `config` viene de dispositivos.js.
// No es una factura: la facturación electrónica de ARCA es un módulo aparte.
export default function Recibo({ venta, config }) {
  return (
    <div className={`recibo recibo-${config.ancho}`}>
      <div className="recibo-centro">
        <strong className="recibo-negocio">{config.negocio || 'Mercado'}</strong>
        {config.direccion && <span>{config.direccion}</span>}
      </div>

      <div className="recibo-linea" />
      <div className="recibo-fila"><span>Recibo N° {venta.numero}</span><span>{fechaHora(venta.fecha_hora)}</span></div>
      <div>Atendió: {venta.vendedor}</div>
      {venta.corrige_a && <div>Reemplaza al recibo N° {venta.corrige_a.numero}</div>}
      {venta.anulada && (
        <div className="recibo-anulada">
          {venta.reemplazada_por ? `*** REEMPLAZADO POR EL N° ${venta.reemplazada_por.numero} ***` : '*** ANULADA ***'}
        </div>
      )}
      <div className="recibo-linea" />

      {venta.items.map((item, i) => (
        <div key={i} className="recibo-item">
          <div>{item.nombre}</div>
          <div className="recibo-fila">
            <span>{cantidad(item.cantidad, item.unidad)} × {pesos(item.precio_unitario)}</span>
            <span>{pesos(item.subtotal)}</span>
          </div>
        </div>
      ))}

      <div className="recibo-linea" />
      <div className="recibo-fila recibo-total"><span>TOTAL</span><span>{pesos(venta.total)}</span></div>
      <div className="recibo-fila"><span>Pago</span><span>{venta.medio_pago_texto}</span></div>
      {venta.cliente && <div className="recibo-fila"><span>Cliente</span><span>{venta.cliente.nombre}</span></div>}
      {venta.paga_con != null && (
        <>
          <div className="recibo-fila"><span>Paga con</span><span>{pesos(venta.paga_con)}</span></div>
          <div className="recibo-fila"><span>Vuelto</span><span>{pesos(venta.vuelto)}</span></div>
        </>
      )}
      <div className="recibo-linea" />

      <div className="recibo-centro">
        {config.pie && <span>{config.pie}</span>}
        <span className="recibo-chico">Comprobante no válido como factura</span>
      </div>
    </div>
  )
}
