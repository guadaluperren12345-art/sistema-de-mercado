# Diagramas de secuencia: productos

Cómo viaja un pedido entre las capas del sistema cuando alguien **consulta**, **da de alta** o **da de baja** un producto. Están hechos a partir del código real (`frontend/src/paginas/Productos.jsx`, `NuevoProducto.jsx`, `Stock.jsx`, `frontend/src/api.js`, `backend/productos/api.py`, `backend/usuarios/permisos.py` y `backend/turnos/autenticacion.py`).

## Las capas

| Capa | Qué es | Archivos |
| --- | --- | --- |
| Pantalla | Lo que se ve en el navegador (React) | `Productos.jsx`, `NuevoProducto.jsx`, `Stock.jsx` |
| Cliente de la API | Agrega el token a cada pedido y lo renueva si venció | `api.js` |
| Proxy de Vite | Recibe `/api/...` en el puerto 5173 y lo pasa al backend | `vite.config.js` |
| Autenticación y permisos | Verifica quién es, su turno y su rol | `AutenticacionConTurno`, `EsEncargadoOAdministrador`, `PasswordAlDia` |
| Vista | Recibe el pedido y coordina | `ProductosViewSet` |
| Serializer | Valida los datos y arma la respuesta | `ProductoSerializer` |
| Modelos (ORM) | Convierten los objetos en consultas SQL | `Producto`, `Categoria`, `Seccion`, `CambioProducto` |
| Base de datos | SQL Server | tablas `producto`, `categoria`, `seccion`, `cambio_producto` |

Quién puede hacer cada cosa:

| Operación | Quién |
| --- | --- |
| Ver los productos | Todos (los empleados no reciben el precio de costo) |
| Dar de alta | Dueños y encargados |
| Dar de baja y reactivar | Dueños y encargados |

Productos y Stock son la misma lista: las dos pantallas hacen el mismo pedido de obtención.

## 1. Obtención: ver la lista de productos

```mermaid
sequenceDiagram
    actor Usuario
    participant Pantalla as Pantalla Productos o Stock (React)
    participant Cliente as Cliente de la API (api.js)
    participant Proxy as Proxy de Vite
    participant Auth as Autenticación y turno
    participant Vista as ProductosViewSet
    participant Ser as ProductoSerializer
    participant ORM as Modelo Producto (ORM)
    participant BD as SQL Server

    Usuario->>Pantalla: Abre Productos o Stock
    Pantalla->>Cliente: api GET /api/productos/
    Cliente->>Proxy: GET /api/productos/ con el token Bearer
    Proxy->>Auth: Pasa el pedido al backend
    Auth->>BD: Busca al usuario y su turno abierto
    BD-->>Auth: Usuario, rol y turno
    Note over Auth: Alcanza con tener sesión.<br/>No hace falta ser encargado
    Auth->>Vista: list
    Note over Vista: Aplica los filtros que vengan,<br/>sección, categoría, activo o texto buscado
    Vista->>ORM: Productos con su categoría y sección
    ORM->>BD: SELECT en producto, categoria y seccion
    BD-->>ORM: Filas
    ORM-->>Vista: Lista de productos
    Vista->>Ser: Convertir a JSON
    Note over Ser: Calcula el semáforo del stock.<br/>Si quien pregunta es empleado, saca el precio de costo
    Ser-->>Vista: Productos con precio, stock y semáforo
    Vista-->>Proxy: 200 con la lista
    Proxy-->>Cliente: 200 con la lista
    Cliente-->>Pantalla: Lista de productos
    Pantalla-->>Usuario: Muestra los productos por sección
```

Los filtros por sección, las pestañas y el buscador de la pantalla no vuelven a llamar al servidor: trabajan sobre la lista que ya llegó. Stock pide la lista con `activo=1` para ver solo los que están a la venta.

## 2. Alta: crear un producto

```mermaid
sequenceDiagram
    actor Encargado
    participant Pantalla as Pantalla Nuevo producto (React)
    participant Cliente as Cliente de la API (api.js)
    participant Proxy as Proxy de Vite
    participant Permisos as Autenticación y permisos
    participant Vista as ProductosViewSet
    participant Ser as ProductoSerializer
    participant ORM as Modelos Producto y CambioProducto
    participant BD as SQL Server

    Encargado->>Pantalla: Abre Nuevo producto
    Pantalla->>Cliente: api GET /api/secciones/
    Cliente-->>Pantalla: Las 3 secciones con sus categorías
    Encargado->>Pantalla: Completa nombre, sección, categoría,<br/>unidad, costo y precio de venta
    Pantalla->>Pantalla: Revisa los datos y muestra el margen
    Pantalla->>Cliente: api POST /api/productos/
    Cliente->>Proxy: POST /api/productos/ con el token Bearer
    Proxy->>Permisos: Pasa el pedido al backend
    Note over Permisos: Tiene que ser encargado o dueño.<br/>A un empleado le responde 403
    Permisos->>Vista: create
    Vista->>Ser: Validar los datos
    Note over Ser: Ordena el nombre y controla precios,<br/>códigos y en qué llega
    Ser->>BD: Consulta si ya hay otro con ese nombre<br/>en la sección o con ese código
    BD-->>Ser: No hay

    alt Algún dato está mal
        Ser-->>Vista: Errores por campo
        Vista-->>Pantalla: 400 con los mensajes
        Pantalla-->>Encargado: Marca el campo con el error
    else Todo bien
        Note over Vista,BD: Una sola transacción
        Ser->>ORM: Crear el producto con stock 0
        ORM->>BD: INSERT en producto
        Vista->>ORM: Registrar el alta con sus precios
        ORM->>BD: INSERT en cambio_producto, acción ALTA
        Vista-->>Proxy: 201 con el producto creado
        Proxy-->>Cliente: 201
        Cliente-->>Pantalla: Producto creado
        Pantalla-->>Encargado: Avisa y queda lista para cargar otro
    end
```

Puntos a tener en cuenta:

- **Nace con stock 0.** El stock se carga después desde Stock (recibir mercadería o recuento), nunca a mano en el producto.
- **Nombre repetido:** no puede haber dos productos con el mismo nombre en la misma sección, aunque uno esté dado de baja; en ese caso el mensaje sugiere reactivarlo.
- **Otras dos formas de alta** usan la misma validación: desde Stock («+ Agregar un producto nuevo», que hace este mismo pedido y después abre Recibir mercadería) y desde Compras a comerciantes («+ Es un producto nuevo», donde el producto se crea dentro de la misma transacción que la compra).

## 3. Baja: dar de baja un producto

```mermaid
sequenceDiagram
    actor Encargado
    participant Pantalla as Pantalla Productos (React)
    participant Cliente as Cliente de la API (api.js)
    participant Proxy as Proxy de Vite
    participant Permisos as Autenticación y permisos
    participant Vista as ProductosViewSet
    participant ORM as Modelos Producto y CambioProducto
    participant BD as SQL Server

    Encargado->>Pantalla: Toca Dar de baja
    Pantalla-->>Encargado: Pide confirmar y un motivo opcional
    Encargado->>Pantalla: Confirma
    Pantalla->>Cliente: api POST /api/productos/ID/desactivar/
    Cliente->>Proxy: POST con el token Bearer y el motivo
    Proxy->>Permisos: Pasa el pedido al backend
    Note over Permisos: Tiene que ser encargado o dueño
    Permisos->>Vista: desactivar
    Vista->>ORM: Buscar el producto
    ORM->>BD: SELECT en producto
    BD-->>Vista: Producto

    alt Ya estaba dado de baja
        Vista-->>Pantalla: 400 con el mensaje
        Pantalla-->>Encargado: Muestra el mensaje
    else Se puede
        Note over Vista,BD: Una sola transacción
        Vista->>ORM: Marcar activo en falso
        ORM->>BD: UPDATE producto
        Vista->>ORM: Registrar la baja con el motivo
        ORM->>BD: INSERT en cambio_producto, acción BAJA
        Vista-->>Proxy: 200 con el producto actualizado
        Proxy-->>Cliente: 200
        Cliente-->>Pantalla: Producto dado de baja
        Pantalla-->>Encargado: Pasa a la pestaña Dados de baja
    end
```

El producto **no se borra**: queda con `activo` en falso. Deja de aparecer en la venta y en Stock, pero conserva su stock, sus ventas anteriores y su historial. Se puede reactivar con `POST /api/productos/ID/reactivar/`, que hace el camino inverso y registra la acción `REACTIVACION`.

## Casos comunes a los tres

El token vencido (se renueva solo y se repite el pedido) está explicado en [`diagrama-secuencia-usuarios.md`](diagrama-secuencia-usuarios.md), y el turno cerrado (el pedido se rechaza y vuelve al inicio de sesión) en [`diagrama-secuencia-ventas.md`](diagrama-secuencia-ventas.md). Funcionan igual acá.
