# Diagramas de secuencia: precios

Cómo viaja un pedido entre las capas del sistema cuando alguien **consulta** los precios de una categoría, **ve cómo quedarían** con un porcentaje, **aplica el cambio** a toda la categoría o **cambia el precio de un solo producto**. Están hechos a partir del código real (`frontend/src/paginas/Precios.jsx`, `frontend/src/api.js`, `backend/productos/api.py` y `backend/productos/models.py`).

## En qué se diferencia de los otros módulos

Acá no hay alta ni baja: los precios no se crean ni se eliminan, **se modifican**. Un producto nace con su precio en el módulo Productos, y este módulo es el único lugar donde después se cambia.

Lo particular es que el cambio por categoría tiene **dos pasos con el mismo pedido**: primero el servidor calcula cómo quedaría cada precio sin guardar nada (vista previa), y recién cuando la persona confirma, lo guarda.

## Las capas

| Capa | Qué es | Archivos |
| --- | --- | --- |
| Pantalla | Lo que se ve en el navegador (React) | `Precios.jsx` |
| Cliente de la API | Agrega el token a cada pedido y lo renueva si venció | `api.js` |
| Proxy de Vite | Recibe `/api/...` en el puerto 5173 y lo pasa al backend | `vite.config.js` |
| Autenticación y permisos | Verifica quién es, su turno y que sea encargado o dueño | `AutenticacionConTurno`, `EsEncargadoOAdministrador`, `PasswordAlDia` |
| Vista | Recibe el pedido y coordina | `PreciosViewSet`, `ProductosViewSet` |
| Serializer | Valida el porcentaje y los precios | `AjustePreciosSerializer`, `PrecioSerializer` |
| Reglas de precios | Hacen la cuenta y guardan el cambio con su registro | `aplicar_porcentaje`, `guardar_precios` |
| Modelos (ORM) | Convierten los objetos en consultas SQL | `Producto`, `Categoria`, `CambioProducto` |
| Base de datos | SQL Server | tablas `producto`, `categoria`, `cambio_producto` |

El módulo es **solo para dueños y encargados**. Un empleado no lo ve en el inicio y, si lo intenta, recibe un error 403. El encargado solo puede usarlo mientras su turno está abierto, porque sin turno no tiene sesión.

Cómo está organizado lo que se vende: **sección** (Almacén, Carnicería, Verdulería) → **categoría** (por ejemplo, Pollo) → **producto** (pechuga, alitas, milanesas). El cambio por porcentaje se aplica a una categoría.

## 1. Obtención: ver los precios de una categoría

```mermaid
sequenceDiagram
    actor Encargado
    participant Pantalla as Pantalla Precios (React)
    participant Cliente as Cliente de la API (api.js)
    participant Proxy as Proxy de Vite
    participant Auth as Autenticación y turno
    participant Vista as ProductosViewSet
    participant Ser as ProductoSerializer
    participant BD as SQL Server

    Encargado->>Pantalla: Abre Precios

    par Secciones con sus categorías
        Pantalla->>Cliente: api GET /api/secciones/
    and Productos a la venta
        Pantalla->>Cliente: api GET /api/productos/ con activo=1
    end

    Cliente->>Proxy: GET con el token Bearer
    Proxy->>Auth: Pasa el pedido al backend
    Auth->>BD: Busca al usuario y su turno abierto
    BD-->>Auth: Usuario, rol y turno
    Auth->>Vista: list
    Vista->>BD: SELECT en producto, categoria y seccion
    BD-->>Vista: Productos activos
    Vista->>Ser: Convertir a JSON
    Note over Ser: Incluye el precio de costo,<br/>porque quien pregunta es encargado o dueño
    Ser-->>Vista: Productos con precio de venta y costo
    Vista-->>Proxy: 200 con la lista
    Proxy-->>Cliente: 200
    Cliente-->>Pantalla: Productos y secciones

    Encargado->>Pantalla: Elige la sección y después la categoría
    Pantalla->>Pantalla: Filtra los productos de esa categoría<br/>y los deja todos tildados
    Pantalla-->>Encargado: Tabla con costo, precio de venta y margen
```

Elegir la sección y la categoría no vuelve a llamar al servidor: la pantalla filtra los productos que ya trajo. El margen lo calcula la pantalla con el precio y el costo.

## 2. Vista previa: cómo quedarían los precios

Se dispara sola un momento después de que la persona deja de escribir. **No guarda nada.**

```mermaid
sequenceDiagram
    actor Encargado
    participant Pantalla as Pantalla Precios (React)
    participant Cliente as Cliente de la API (api.js)
    participant Permisos as Autenticación y permisos
    participant Vista as PreciosViewSet
    participant Ser as AjustePreciosSerializer
    participant Reglas as Reglas de precios
    participant BD as SQL Server

    Encargado->>Pantalla: Elige Subir o Bajar, escribe el porcentaje,<br/>qué cambia y el redondeo
    Pantalla->>Pantalla: Espera 300 milisegundos sin cambios
    Pantalla->>Cliente: api POST /api/precios/ajuste/ sin confirmar
    Cliente->>Permisos: POST con el token Bearer
    Note over Permisos: Tiene que ser encargado o dueño
    Permisos->>Vista: ajuste
    Vista->>Ser: Validar los datos
    Note over Ser: El porcentaje no puede ser 0,<br/>ni bajar más de 90, ni subir más de 500.<br/>El redondeo tiene que ser uno de la lista

    alt Algún dato está mal
        Ser-->>Vista: Errores por campo
        Vista-->>Pantalla: 400 con el mensaje
        Pantalla-->>Encargado: Muestra el mensaje bajo el formulario
    else Datos correctos
        Vista->>BD: SELECT de los productos tildados<br/>de esa categoría que están a la venta
        BD-->>Vista: Productos, sin bloquearlos
        loop Por cada producto
            Vista->>Reglas: aplicar_porcentaje al precio de venta,<br/>al costo o a los dos
            Note over Reglas: El precio de venta se redondea<br/>si se pidió. El costo no se redondea
            Reglas-->>Vista: Precio nuevo
        end
        Vista-->>Cliente: 200 con el precio de ahora y el nuevo de cada uno
        Cliente-->>Pantalla: Vista previa
        Pantalla-->>Encargado: Precio de ahora tachado y el nuevo en rosa.<br/>Avisa si alguno queda por debajo del costo
    end
```

Si la persona sigue cambiando el formulario, la respuesta de una vista previa vieja se descarta cuando llega. La cuenta la hace siempre el servidor, no la pantalla, para que lo que se ve antes de confirmar sea exactamente lo que se va a guardar.

## 3. Modificación: aplicar el cambio a la categoría

Es el mismo pedido que la vista previa, pero con `confirmar`.

```mermaid
sequenceDiagram
    actor Encargado
    participant Pantalla as Pantalla Precios (React)
    participant Cliente as Cliente de la API (api.js)
    participant Proxy as Proxy de Vite
    participant Permisos as Autenticación y permisos
    participant Vista as PreciosViewSet
    participant Ser as AjustePreciosSerializer
    participant Reglas as Reglas de precios
    participant BD as SQL Server

    Encargado->>Pantalla: Toca Aplicar
    Pantalla-->>Encargado: Pregunta si sube o baja ese porcentaje<br/>a esa cantidad de productos
    Encargado->>Pantalla: Confirma
    Pantalla->>Cliente: api POST /api/precios/ajuste/ con confirmar
    Cliente->>Proxy: POST con el token Bearer
    Proxy->>Permisos: Pasa el pedido al backend
    Note over Permisos: Tiene que ser encargado o dueño.<br/>A un empleado le responde 403
    Permisos->>Vista: ajuste
    Vista->>Ser: Validar los datos de nuevo
    Ser-->>Vista: Datos válidos

    Note over Vista,BD: Una sola transacción
    Vista->>BD: SELECT con bloqueo de los productos<br/>tildados de esa categoría
    BD-->>Vista: Productos bloqueados

    alt No hay productos para cambiar
        Vista-->>Pantalla: 400 con el mensaje
        Pantalla-->>Encargado: Muestra el mensaje
    else Hay productos
        loop Por cada producto
            Vista->>Reglas: aplicar_porcentaje
            Reglas-->>Vista: Precio nuevo
            Vista->>Reglas: guardar_precios
            opt El precio cambió
                Reglas->>BD: UPDATE producto con el precio nuevo
                Reglas->>BD: INSERT en cambio_producto, acción PRECIO,<br/>con el precio de antes y el de ahora
            end
        end
        Vista-->>Proxy: 200 con cuántos cambiaron
        Proxy-->>Cliente: 200
        Cliente-->>Pantalla: Cambio aplicado
        Pantalla->>Cliente: api GET /api/productos/, vuelve a pedir la lista
        Pantalla-->>Encargado: Avisa cuántos precios cambió<br/>y muestra los nuevos
    end
```

Puntos a tener en cuenta:

- **Se vuelve a calcular todo.** Al confirmar, el servidor no usa los números de la vista previa: parte otra vez del precio que el producto tiene en ese instante, ya bloqueado. Si alguien cambió un precio entre medio, se aplica sobre el valor nuevo.
- **Todo o nada.** Si falla un producto, no se cambia ninguno.
- **Solo los que están a la venta.** Los productos dados de baja no cambian con el ajuste por categoría.
- **Las ventas ya hechas no cambian.** Cada recibo guardó el precio de su momento.
- **Queda registrado, producto por producto**, con un detalle como «Venta $6500.00 → $7800.00 · +20 % a toda la categoría Pollo», y se ve en la Actividad del sistema.

## 4. Modificación: cambiar el precio de un solo producto

```mermaid
sequenceDiagram
    actor Encargado
    participant Pantalla as Pantalla Precios (React)
    participant Cliente as Cliente de la API (api.js)
    participant Proxy as Proxy de Vite
    participant Permisos as Autenticación y permisos
    participant Vista as ProductosViewSet
    participant Ser as PrecioSerializer
    participant Reglas as Reglas de precios
    participant BD as SQL Server

    Encargado->>Pantalla: Toca Cambiar en la fila de un producto
    Pantalla-->>Encargado: Abre el costo y el precio para escribirlos
    Encargado->>Pantalla: Escribe los valores nuevos y toca Guardar
    Pantalla->>Pantalla: Revisa que el precio sea mayor a 0<br/>y el costo no sea negativo
    Pantalla->>Cliente: api POST /api/productos/ID/precio/
    Cliente->>Proxy: POST con el token Bearer
    Proxy->>Permisos: Pasa el pedido al backend
    Note over Permisos: Tiene que ser encargado o dueño
    Permisos->>Vista: precio
    Vista->>Ser: Validar precio de venta y costo

    alt Algún dato está mal
        Ser-->>Vista: Errores por campo
        Vista-->>Pantalla: 400 con el mensaje
        Pantalla-->>Encargado: Muestra el mensaje
    else Datos correctos
        Note over Vista,BD: Una sola transacción
        Vista->>BD: SELECT con bloqueo del producto
        BD-->>Vista: Producto
        Vista->>Reglas: guardar_precios

        alt Los precios son iguales a los de ahora
            Reglas-->>Vista: No cambió nada
            Vista-->>Pantalla: 400, no hay nada que cambiar
        else Algo cambió
            Reglas->>BD: UPDATE producto
            Reglas->>BD: INSERT en cambio_producto, acción PRECIO,<br/>detalle cambio individual
            Vista-->>Proxy: 200 con el producto actualizado
            Proxy-->>Cliente: 200
            Cliente-->>Pantalla: Producto con su precio nuevo
            Pantalla-->>Encargado: Avisa a cuánto sale ahora
        end
    end
```

Se puede mandar solo el precio de venta, solo el costo, o los dos. Si el precio de venta queda por debajo del costo, la pantalla lo marca en rojo pero deja guardarlo.

## Qué no cambia los precios

Para no confundir, estas operaciones **no** tocan el precio de un producto:

| Operación | Qué pasa con el precio |
| --- | --- |
| Editar un producto (nombre, código, categoría) | Si se mandan precios, el servidor los ignora |
| Recibir mercadería con otro costo | El costo queda en el movimiento de stock, no en el producto |
| Anotar una compra a un comerciante | Igual: el costo queda en la compra y en el movimiento |
| Crear un producto nuevo | Es la única vez que el precio se pone fuera de este módulo |

## Casos comunes

El token vencido está en [`diagrama-secuencia-usuarios.md`](diagrama-secuencia-usuarios.md) y el turno cerrado en [`diagrama-secuencia-ventas.md`](diagrama-secuencia-ventas.md). Cómo se toma el precio al cobrar está también en el de ventas, y cómo nace un producto con su precio, en [`diagrama-secuencia-productos.md`](diagrama-secuencia-productos.md).
