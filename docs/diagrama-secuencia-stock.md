# Diagramas de secuencia: stock

Cómo viaja un pedido entre las capas del sistema cuando alguien **consulta** el stock, cuando se **da de alta** mercadería (se recibe), cuando se **da de baja** (se pierde) y cuando se hace un **recuento**. Están hechos a partir del código real (`frontend/src/paginas/Stock.jsx`, `frontend/src/componentes/FormularioStock.jsx`, `frontend/src/paginas/MovimientosStock.jsx`, `frontend/src/presentaciones.js`, `frontend/src/api.js`, `backend/productos/api.py` y `backend/productos/models.py`).

## Las capas

| Capa | Qué es | Archivos |
| --- | --- | --- |
| Pantalla | Lo que se ve en el navegador (React) | `Stock.jsx`, `FormularioStock.jsx`, `MovimientosStock.jsx` |
| Cliente de la API | Agrega el token a cada pedido y lo renueva si venció | `api.js` |
| Proxy de Vite | Recibe `/api/...` en el puerto 5173 y lo pasa al backend | `vite.config.js` |
| Autenticación y permisos | Verifica quién es, su turno y su rol | `AutenticacionConTurno`, `EsEncargadoOAdministrador`, `PasswordAlDia` |
| Vista | Recibe el pedido y coordina | `ProductosViewSet`, `MovimientosViewSet` |
| Serializer | Valida las cantidades y arma la respuesta | `IngresoSerializer`, `PerdidaSerializer`, `AjusteSerializer`, `ProductoSerializer` |
| Reglas de stock | Cambian el stock dejando siempre un movimiento | `registrar_movimiento`, `leer_bultos`, `recordar_presentacion` |
| Modelos (ORM) | Convierten los objetos en consultas SQL | `Producto`, `MovimientoStock`, `CambioProducto` |
| Base de datos | SQL Server | tablas `producto`, `movimiento_stock`, `cambio_producto` |

La regla central del módulo: **nadie escribe el stock a mano**. El número que se ve solo cambia a través de un movimiento, y cada movimiento guarda cuánto entró o salió, cómo quedó el stock, a qué costo, quién lo hizo, en qué turno y cuándo.

Los cuatro tipos de movimiento:

| Tipo | Cuándo | Efecto |
| --- | --- | --- |
| `INGRESO` | Llegó mercadería (desde Stock o desde una compra a un comerciante) | Suma |
| `PERDIDA` | Se venció, se rompió o está en mal estado | Resta |
| `AJUSTE` | Un recuento no coincidió con lo que decía el sistema | Suma o resta la diferencia |
| `VENTA` | Se vendió, o se anuló una venta | Resta, o devuelve |

Quién puede hacer cada cosa:

| Operación | Quién |
| --- | --- |
| Ver el stock | Todos (los empleados no reciben los costos) |
| Recibir mercadería, registrar pérdidas, hacer recuentos y cambiar el mínimo | Dueños y encargados |
| Ver el historial de movimientos | Dueños y encargados |

## 1. Obtención: ver el stock

```mermaid
sequenceDiagram
    actor Usuario
    participant Pantalla as Pantalla Stock (React)
    participant Cliente as Cliente de la API (api.js)
    participant Proxy as Proxy de Vite
    participant Auth as Autenticación y turno
    participant Vista as ProductosViewSet
    participant Ser as ProductoSerializer
    participant ORM as Modelo Producto (ORM)
    participant BD as SQL Server

    Usuario->>Pantalla: Abre Stock

    par Secciones
        Pantalla->>Cliente: api GET /api/secciones/
    and Productos a la venta
        Pantalla->>Cliente: api GET /api/productos/ con activo=1
    end

    Cliente->>Proxy: GET con el token Bearer
    Proxy->>Auth: Pasa el pedido al backend
    Auth->>BD: Busca al usuario y su turno abierto
    BD-->>Auth: Usuario, rol y turno
    Note over Auth: Alcanza con tener sesión
    Auth->>Vista: list
    Vista->>ORM: Productos activos con su categoría y sección
    ORM->>BD: SELECT en producto, categoria y seccion
    BD-->>ORM: Filas con stock actual y stock mínimo
    ORM-->>Vista: Lista de productos
    Vista->>Ser: Convertir a JSON
    Note over Ser: Calcula el semáforo de cada uno.<br/>Rojo sin stock, amarillo en el mínimo o menos,<br/>verde por encima
    Ser-->>Vista: Productos con stock, semáforo y en qué llegan
    Vista-->>Proxy: 200 con la lista
    Proxy-->>Cliente: 200
    Cliente-->>Pantalla: Productos y secciones
    Pantalla->>Pantalla: Ordena, primero lo que falta
    Pantalla-->>Usuario: Lista con el color de cada producto
```

El stock no se calcula al consultar: está guardado en el producto (`stock_actual`) y cada movimiento lo actualiza, así la lista es rápida. Los filtros por sección y por color, el buscador y el cambio entre «ver en unidades y kilos» y «ver en cajas, cajones, bandejas…» los resuelve la pantalla con lo que ya llegó, sin volver a llamar al servidor. Es la misma lista que usa la pantalla Productos.

## 2. Alta: recibir mercadería

```mermaid
sequenceDiagram
    actor Encargado
    participant Pantalla as Pantalla Stock (React)
    participant Cliente as Cliente de la API (api.js)
    participant Proxy as Proxy de Vite
    participant Permisos as Autenticación y permisos
    participant Vista as ProductosViewSet
    participant Ser as IngresoSerializer
    participant Reglas as Reglas de stock
    participant BD as SQL Server

    Encargado->>Pantalla: Toca Recibir mercadería en un producto
    Encargado->>Pantalla: Elige en qué lo cuenta, kilo, unidad,<br/>caja, cajón, y escribe cuánto llegó
    Pantalla-->>Encargado: Muestra cómo va a quedar el stock
    Encargado->>Pantalla: Toca Sumar al stock
    Pantalla->>Cliente: api POST /api/productos/ID/ingreso/
    Cliente->>Proxy: POST con el token Bearer
    Proxy->>Permisos: Pasa el pedido al backend
    Note over Permisos: Tiene que ser encargado o dueño.<br/>A un empleado le responde 403
    Permisos->>Vista: ingreso
    Vista->>BD: SELECT del producto
    BD-->>Vista: Producto
    Vista->>Ser: Validar la cantidad

    opt Vino por caja o cajón
        Ser->>Reglas: leer_bultos
        Note over Reglas: Multiplica cuántos por cuánto trae cada uno.<br/>3 cajones de 18 kg son 54 kg
        Reglas-->>Ser: Total en kilos o unidades y el detalle
    end

    alt Algún dato está mal
        Note over Ser: Falta la cantidad, es 0 o negativa,<br/>o tiene decimales y el producto va por unidad
        Ser-->>Vista: Errores por campo
        Vista-->>Pantalla: 400 con los mensajes
        Pantalla-->>Encargado: Muestra el mensaje
    else Todo bien
        Note over Vista,BD: Una sola transacción
        opt Estaba como suelto y llegó en cajón
            Vista->>Reglas: recordar_presentacion
            Reglas->>BD: UPDATE producto e INSERT en cambio_producto
        end
        Vista->>Reglas: registrar_movimiento
        Reglas->>BD: SELECT con bloqueo del producto
        BD-->>Reglas: Producto con su stock de ahora
        Reglas->>BD: UPDATE producto, suma al stock
        Reglas->>BD: INSERT en movimiento_stock, tipo INGRESO,<br/>con el stock resultante y el costo
        Reglas-->>Vista: Producto actualizado
        Vista-->>Proxy: 200 con el producto
        Proxy-->>Cliente: 200
        Cliente-->>Pantalla: Producto con su stock nuevo
        Pantalla-->>Encargado: Cambia la cantidad y, si corresponde, el color
    end
```

Puntos a tener en cuenta:

- **El bloqueo del producto** hace que dos personas cargando a la vez, o una caja vendiendo mientras tanto, no pisen el stock: cada operación espera a que termine la anterior.
- **El costo** de esa entrega es opcional; si no se escribe, vale el costo que ya tiene el producto. Queda guardado en el movimiento, pero no cambia el precio del producto.
- **Por caja o cajón:** el stock se guarda siempre en kilos o unidades. El movimiento anota cómo llegó («3 cajones × 18 kg»).
- **Un producto que todavía no existe** se crea con «+ Agregar un producto nuevo» y después se le carga cuánto hay con este mismo recorrido. Está en [`diagrama-secuencia-productos.md`](diagrama-secuencia-productos.md).
- **Una compra a un comerciante** también suma al stock por este camino. Está en [`diagrama-secuencia-compras-comerciantes.md`](diagrama-secuencia-compras-comerciantes.md).

## 3. Baja: registrar una pérdida

```mermaid
sequenceDiagram
    actor Encargado
    participant Pantalla as Pantalla Stock (React)
    participant Cliente as Cliente de la API (api.js)
    participant Proxy as Proxy de Vite
    participant Permisos as Autenticación y permisos
    participant Vista as ProductosViewSet
    participant Ser as PerdidaSerializer
    participant Reglas as Reglas de stock
    participant BD as SQL Server

    Encargado->>Pantalla: Toca Pérdida en un producto
    Note over Pantalla: El botón está apagado<br/>si el producto no tiene stock
    Encargado->>Pantalla: Escribe cuánto se perdió y elige el motivo,<br/>vencido, en mal estado, rotura, robo u otro
    Pantalla->>Cliente: api POST /api/productos/ID/perdida/
    Cliente->>Proxy: POST con el token Bearer
    Proxy->>Permisos: Pasa el pedido al backend
    Note over Permisos: Tiene que ser encargado o dueño
    Permisos->>Vista: perdida
    Vista->>Ser: Validar cantidad y motivo
    Note over Ser: El motivo es obligatorio.<br/>Si vino por cajón, calcula el total

    alt Falta un dato
        Ser-->>Vista: Errores por campo
        Vista-->>Pantalla: 400 con los mensajes
        Pantalla-->>Encargado: Muestra el mensaje
    else Datos correctos
        Note over Vista,BD: Una sola transacción
        Vista->>Reglas: registrar_movimiento
        Reglas->>BD: SELECT con bloqueo del producto
        BD-->>Reglas: Producto con su stock de ahora

        alt Se perdió más de lo que hay
            Reglas-->>Vista: Error, primero hacé un recuento
            Vista-->>Pantalla: 400 con el mensaje
            Pantalla-->>Encargado: Dice cuánto hay en el sistema
        else Hay stock suficiente
            Reglas->>BD: UPDATE producto, resta del stock
            Reglas->>BD: INSERT en movimiento_stock, tipo PERDIDA,<br/>con el motivo y el costo
            Vista-->>Proxy: 200 con el producto
            Proxy-->>Cliente: 200
            Cliente-->>Pantalla: Producto con su stock nuevo
            Pantalla-->>Encargado: Baja la cantidad y puede cambiar el color
        end
    end
```

La pérdida se valoriza al costo del producto en ese momento. Ese valor es el que después aparece como «Pérdidas de mercadería» en el Resumen y el que se resta en Resultados por sección. No se puede perder más de lo que el sistema tiene: si en la realidad hay otra cantidad, primero se hace un recuento.

## 4. Recuento: corregir el stock

Cuando lo que se cuenta a mano no coincide con lo que dice el sistema.

```mermaid
sequenceDiagram
    actor Encargado
    participant Pantalla as Pantalla Stock (React)
    participant Cliente as Cliente de la API (api.js)
    participant Permisos as Autenticación y permisos
    participant Vista as ProductosViewSet
    participant Ser as AjusteSerializer
    participant Reglas as Reglas de stock
    participant BD as SQL Server

    Encargado->>Pantalla: Toca Recuento en un producto
    Encargado->>Pantalla: Escribe cuánto hay en realidad<br/>y elige el motivo
    Pantalla-->>Encargado: Muestra la diferencia que se va a corregir
    Encargado->>Pantalla: Toca Guardar recuento
    Pantalla->>Cliente: api POST /api/productos/ID/ajuste/
    Cliente->>Permisos: POST con el token Bearer
    Note over Permisos: Tiene que ser encargado o dueño
    Permisos->>Vista: ajuste
    Vista->>Ser: Validar lo contado y el motivo
    Note over Ser: Lo contado no puede ser negativo.<br/>Se puede contar por cajones

    Note over Vista,BD: Una sola transacción
    Vista->>Reglas: registrar_movimiento
    Reglas->>BD: SELECT con bloqueo del producto
    BD-->>Reglas: Producto con su stock de ahora
    Reglas->>Reglas: Calcula la diferencia,<br/>lo contado menos lo que dice el sistema

    alt No hay diferencia
        Reglas-->>Vista: Error, no hay nada que ajustar
        Vista-->>Pantalla: 400 con el mensaje
    else Hay diferencia
        Reglas->>BD: UPDATE producto, el stock queda en lo contado
        Reglas->>BD: INSERT en movimiento_stock, tipo AJUSTE,<br/>con la diferencia y el motivo
        Vista-->>Cliente: 200 con el producto
        Cliente-->>Pantalla: Producto con su stock nuevo
        Pantalla-->>Encargado: El stock queda en lo que se contó
    end
```

La persona escribe **cuánto hay**, no la diferencia: la diferencia la calcula el servidor con el stock del momento, ya bloqueado. El recuento con motivo «Carga inicial de stock» es la forma de cargar lo que ya había cuando se empezó a usar el sistema, sin que cuente como una compra.

El **stock mínimo** (con cuánto hay que avisar que queda poco) se cambia con `PATCH /api/productos/ID/`. No genera un movimiento, porque no cambia cuánto hay: solo cambia a partir de cuándo el producto pasa a amarillo.

## 5. Ver el historial de movimientos

```mermaid
sequenceDiagram
    actor Encargado
    participant Pantalla as Pantalla Movimientos (React)
    participant Cliente as Cliente de la API (api.js)
    participant Permisos as Autenticación y permisos
    participant Vista as MovimientosViewSet
    participant Ser as MovimientoSerializer
    participant BD as SQL Server

    Encargado->>Pantalla: Toca Ver movimientos,<br/>o Historial en un producto
    Pantalla->>Cliente: api GET /api/movimientos/ con los filtros
    Cliente->>Permisos: GET con el token Bearer
    Note over Permisos: Tiene que ser encargado o dueño,<br/>porque el historial incluye costos
    Permisos->>Vista: list
    Note over Vista: Filtra por producto, tipo y fechas
    Vista->>BD: SELECT en movimiento_stock con producto y usuario
    BD-->>Vista: Hasta 300, lo más nuevo primero
    Vista->>Ser: Convertir a JSON
    Ser-->>Vista: Tipo, cantidad con signo, stock resultante,<br/>valor al costo, quién y cuándo
    Vista-->>Cliente: 200 con la lista
    Cliente-->>Pantalla: Movimientos
    Pantalla-->>Encargado: Historial de entradas y salidas
```

Los movimientos son de **solo lectura**: no se modifican ni se borran. Un error se corrige con otro movimiento (un recuento), y los dos quedan en el historial.

## Casos comunes

El token vencido está en [`diagrama-secuencia-usuarios.md`](diagrama-secuencia-usuarios.md) y el turno cerrado en [`diagrama-secuencia-ventas.md`](diagrama-secuencia-ventas.md), donde también está cómo una venta descuenta el stock y una anulación lo devuelve.
