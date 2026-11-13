# Diagramas de secuencia: compras a comerciantes

Cómo viaja un pedido entre las capas del sistema cuando un dueño o un encargado **consulta** las compras, **da de alta** una compra o **da de baja** (anula) una compra. Están hechos a partir del código real (`frontend/src/paginas/Compras.jsx`, `frontend/src/api.js`, `backend/compras/api.py`, `backend/compras/models.py`, `backend/productos/api.py` y `backend/usuarios/permisos.py`).

## Las capas

| Capa | Qué es | Archivos |
| --- | --- | --- |
| Pantalla | Lo que se ve en el navegador (React) | `Compras.jsx` |
| Cliente de la API | Agrega el token a cada pedido y lo renueva si venció | `api.js` |
| Proxy de Vite | Recibe `/api/...` en el puerto 5173 y lo pasa al backend | `vite.config.js` |
| Autenticación y permisos | Verifica quién es y que sea encargado o dueño | `AutenticacionConTurno`, `EsEncargadoOAdministrador`, `PasswordAlDia` |
| Vista | Recibe el pedido y coordina | `ComprasViewSet` |
| Serializer | Valida los datos y arma la respuesta | `NuevaCompraSerializer`, `CompraSerializer` |
| Modelos (ORM) | Convierten los objetos en consultas SQL | `Comerciante`, `Compra`, `PagoCompra`, `Producto`, `MovimientoStock` |
| Base de datos | SQL Server | tablas `comerciante`, `compra`, `pago_compra`, `producto`, `movimiento_stock` |

Las tres operaciones son **solo para dueños y encargados**. Si el que pregunta es un empleado, la capa de permisos corta el pedido con un error 403 antes de llegar a la vista.

## 1. Obtención: ver la lista de compras

```mermaid
sequenceDiagram
    actor Encargado
    participant Pantalla as Pantalla Compras (React)
    participant Cliente as Cliente de la API (api.js)
    participant Proxy as Proxy de Vite
    participant Permisos as Autenticación y permisos
    participant Vista as ComprasViewSet
    participant Ser as CompraSerializer
    participant ORM as Modelos Compra y Comerciante
    participant BD as SQL Server

    Encargado->>Pantalla: Abre Compras a comerciantes
    Pantalla->>Cliente: api GET /api/compras/
    Cliente->>Proxy: GET /api/compras/ con el token Bearer
    Proxy->>Permisos: Pasa el pedido al backend
    Permisos->>BD: Busca al usuario del token
    BD-->>Permisos: Usuario y rol
    Note over Permisos: Token válido y es encargado o dueño
    Permisos->>Vista: list
    Vista->>ORM: Compras con su comerciante, producto y pagos
    ORM->>BD: SELECT en compra, comerciante y pago_compra
    BD-->>ORM: Filas
    ORM-->>Vista: Lista de compras
    Vista->>ORM: Cuánto se le debe a cada comerciante
    ORM->>BD: SELECT con la suma de lo que falta pagar
    BD-->>Vista: Deuda por comerciante
    Vista->>Ser: Convertir a JSON
    Note over Ser: Calcula el estado de cada compra,<br/>pagado, falta una parte o sin pagar
    Ser-->>Vista: Compras con su estado
    Vista-->>Proxy: 200 con la lista y la deuda
    Proxy-->>Cliente: 200 con la lista y la deuda
    Cliente-->>Pantalla: Lista de compras
    Pantalla-->>Encargado: Muestra cada compra en verde,<br/>amarillo o rojo
```

Con `?estado=`, `?comerciante=` o fechas, la vista filtra antes de consultar. El color lo pone la pantalla según el estado: verde pagado, amarillo falta una parte, rojo sin pagar.

## 2. Alta: anotar una compra

```mermaid
sequenceDiagram
    actor Encargado
    participant Pantalla as Pantalla Compras (React)
    participant Cliente as Cliente de la API (api.js)
    participant Proxy as Proxy de Vite
    participant Permisos as Autenticación y permisos
    participant Vista as ComprasViewSet
    participant Ser as NuevaCompraSerializer
    participant ORM as Modelos (ORM)
    participant BD as SQL Server

    Encargado->>Pantalla: Completa comerciante, producto,<br/>cantidad, costo y cómo quedó el pago
    Pantalla->>Pantalla: Revisa que no falte nada
    Pantalla->>Cliente: api POST /api/compras/
    Cliente->>Proxy: POST /api/compras/ con el token Bearer
    Proxy->>Permisos: Pasa el pedido al backend
    Note over Permisos: Token válido y es encargado o dueño
    Permisos->>Vista: create
    Vista->>Ser: Validar los datos
    Ser->>BD: Consulta que el producto exista
    BD-->>Ser: Producto
    Note over Ser: Controla que esté a la venta, la cantidad,<br/>el costo y que lo pagado no pase del costo

    alt Algún dato está mal
        Ser-->>Vista: Errores por campo
        Vista-->>Pantalla: 400 con los mensajes
        Pantalla-->>Encargado: Marca el campo con el error
    else Todo bien
        Note over Vista,BD: Una sola transacción
        Vista->>ORM: Buscar o crear el comerciante
        ORM->>BD: SELECT o INSERT en comerciante
        Vista->>ORM: Crear la compra con fecha y hora del sistema
        ORM->>BD: INSERT en compra
        Vista->>ORM: Sumar la mercadería al stock
        ORM->>BD: UPDATE producto e INSERT en movimiento_stock
        opt Se pagó todo o una parte
            Vista->>ORM: Registrar el pago
            ORM->>BD: INSERT en pago_compra y UPDATE compra
        end
        Vista-->>Proxy: 201 con la compra creada
        Proxy-->>Cliente: 201
        Cliente-->>Pantalla: Compra creada
        Pantalla-->>Encargado: Aparece en la lista con su color
    end
```

La fecha y la hora no se escriben: las pone el sistema al guardar. Si cualquier paso falla, no queda nada guardado, ni la compra, ni el stock, ni el pago.

## 3. Baja: anular una compra

```mermaid
sequenceDiagram
    actor Encargado
    participant Pantalla as Pantalla Compras (React)
    participant Cliente as Cliente de la API (api.js)
    participant Proxy as Proxy de Vite
    participant Permisos as Autenticación y permisos
    participant Vista as ComprasViewSet
    participant ORM as Modelos Compra, Producto y MovimientoStock
    participant BD as SQL Server

    Encargado->>Pantalla: Toca Anular
    Pantalla-->>Encargado: Pide confirmar y el motivo
    Encargado->>Pantalla: Escribe el motivo y confirma
    Pantalla->>Cliente: api POST /api/compras/ID/anular/
    Cliente->>Proxy: POST con el token Bearer y el motivo
    Proxy->>Permisos: Pasa el pedido al backend
    Note over Permisos: Token válido y es encargado o dueño
    Permisos->>Vista: anular
    Vista->>ORM: Buscar la compra
    ORM->>BD: SELECT con bloqueo en compra
    BD-->>Vista: Compra

    alt No se puede anular
        Note over Vista: Falta el motivo, la compra no existe<br/>o ya estaba anulada
        Vista-->>Pantalla: 400 o 404 con el motivo
        Pantalla-->>Encargado: Muestra el mensaje
    else Se puede
        Note over Vista,BD: Una sola transacción
        Vista->>ORM: Descontar del stock lo que había sumado
        ORM->>BD: UPDATE producto e INSERT en movimiento_stock
        Vista->>ORM: Marcar la compra como anulada
        ORM->>BD: UPDATE compra con quién, cuándo y por qué
        Vista-->>Proxy: 200 con la compra actualizada
        Proxy-->>Cliente: 200
        Cliente-->>Pantalla: Compra anulada
        Pantalla-->>Encargado: Queda en la lista tachada
    end
```

La compra **no se borra**: queda en la lista como anulada, con quién la anuló y el motivo, y deja de contar en la deuda con el comerciante.

## Qué pasa si el token venció

Igual que en los demás módulos: si el token de acceso ya venció (dura 15 minutos), el cliente lo renueva solo y repite el pedido una vez. El diagrama está en [`diagrama-secuencia-usuarios.md`](diagrama-secuencia-usuarios.md).
