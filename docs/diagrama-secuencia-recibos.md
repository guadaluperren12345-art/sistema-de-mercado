# Diagramas de secuencia: módulo Recibos

Cómo viaja un pedido entre las capas del sistema cuando alguien **consulta el buzón de recibos**, **abre y reimprime** uno, lo **anula** o pasa a **modificarlo**, y cómo el buzón **se limpia solo** cada semana. Están hechos a partir del código real (`frontend/src/paginas/Recibos.jsx`, `frontend/src/componentes/Recibo.jsx`, `frontend/src/dispositivos.js`, `frontend/src/useConsulta.js`, `backend/ventas/api.py` y `backend/turnos/servicios.py`).

## Las capas

| Capa | Qué es | Archivos |
| --- | --- | --- |
| Pantalla | Lo que se ve en el navegador (React) | `Recibos.jsx`, `Recibo.jsx` |
| Impresora | El recibo sale por la impresión del navegador, en 58 u 80 mm | `dispositivos.js` |
| Cliente de la API | Agrega el token a cada pedido y lo renueva si venció | `useConsulta.js`, `api.js` |
| Proxy de Vite | Recibe `/api/...` en el puerto 5173 y lo pasa al backend | `vite.config.js` |
| Autenticación y turno | Verifica quién es, su turno y su rol | `AutenticacionConTurno`, `EsEncargadoOAdministrador`, `PasswordAlDia` |
| Vista | Recibe el pedido y coordina | `VentasViewSet` |
| Serializer | Arma cada recibo para mostrar | `VentaSerializer`, `DetalleSerializer` |
| Planificador | Proceso aparte que limpia el buzón | contenedor `tareas`, `limpiar_buzon` |
| Modelos (ORM) | Convierten los objetos en consultas SQL | `Venta`, `DetalleVenta` |
| Base de datos | SQL Server | tablas `venta`, `detalle_venta` |

Un recibo **no es un dato aparte**: es la misma venta, mostrada con forma de ticket. Por eso este módulo usa las rutas de ventas (`/api/ventas/`).

Quién puede hacer cada cosa:

| Operación | Quién |
| --- | --- |
| Ver recibos y reimprimirlos | Todos. Un empleado ve solo los suyos; encargados y dueños ven todos |
| Modificar una compra | El cajero que la cobró, el mismo día; encargados y dueños, cualquiera |
| Anular | Encargados y dueños |

## 1. Obtención: ver el buzón de recibos

```mermaid
sequenceDiagram
    actor Usuario
    participant Pantalla as Pantalla Recibos (React)
    participant Cliente as Cliente de la API (api.js)
    participant Proxy as Proxy de Vite
    participant Auth as Autenticación y turno
    participant Vista as VentasViewSet
    participant Ser as VentaSerializer
    participant ORM as Modelo Venta (ORM)
    participant BD as SQL Server

    Usuario->>Pantalla: Abre Recibos o elige Hoy, Ayer<br/>o Toda la semana
    Pantalla->>Cliente: api GET /api/ventas/ con desde y hasta
    Cliente->>Proxy: GET con el token Bearer
    Proxy->>Auth: Pasa el pedido al backend
    Auth->>BD: Busca al usuario y su turno abierto
    BD-->>Auth: Usuario, rol y turno
    Auth->>Vista: list

    alt Es empleado
        Note over Vista: Filtra solo las ventas que cobró él
    else Es encargado o dueño
        Note over Vista: Ve las ventas de todos
    end
    Note over Vista: Solo las que siguen en el buzón,<br/>del día pedido, hasta 500

    Vista->>ORM: Ventas con vendedor, cliente,<br/>renglones y correcciones
    ORM->>BD: SELECT en venta y detalle_venta
    BD-->>ORM: Filas
    ORM-->>Vista: Lista de ventas
    Vista->>Ser: Convertir a JSON
    Note over Ser: Agrega el número de recibo, si está anulado,<br/>a cuál reemplaza y si se puede modificar.<br/>No incluye el costo
    Ser-->>Vista: Recibos
    Vista-->>Proxy: 200 con la lista
    Proxy-->>Cliente: 200
    Cliente-->>Pantalla: Recibos
    Pantalla-->>Usuario: Lista agrupada por día,<br/>con la cantidad y el total
```

El buscador (por número de recibo, producto o vendedor) no vuelve a llamar al servidor: filtra la lista que ya llegó. El total que se muestra arriba no cuenta los recibos anulados.

## 2. Abrir un recibo y reimprimirlo

Los datos del recibo ya llegaron con la lista, así que **no hay ningún pedido al servidor**: todo pasa en el navegador.

```mermaid
sequenceDiagram
    actor Usuario
    participant Pantalla as Pantalla Recibos (React)
    participant Recibo as Componente Recibo
    participant Config as Configuración del equipo
    participant Imp as Impresora

    Usuario->>Pantalla: Toca un recibo de la lista
    Pantalla->>Config: Lee nombre del negocio, dirección,<br/>pie y ancho del papel
    Config-->>Pantalla: Configuración guardada en este equipo
    Pantalla->>Recibo: Dibuja el recibo con esa venta
    Recibo-->>Usuario: Recibo en pantalla, con sus productos,<br/>el total y cómo se pagó
    Usuario->>Pantalla: Toca Imprimir
    Pantalla->>Pantalla: Ajusta el tamaño de página a 58 u 80 mm
    Pantalla->>Imp: Impresión del navegador
    Note over Pantalla,Imp: Los estilos de impresión ocultan todo<br/>menos el recibo
    Imp-->>Usuario: Sale el recibo en papel
```

La configuración del recibo se guarda en cada equipo, porque cada caja puede tener otra impresora. Se cambia en la pantalla «Lector e impresora».

## 3. Anular un recibo

```mermaid
sequenceDiagram
    actor Encargado
    participant Pantalla as Pantalla Recibos (React)
    participant Cliente as Cliente de la API (api.js)
    participant Permisos as Autenticación y permisos
    participant Vista as VentasViewSet
    participant Reglas as Reglas de venta
    participant BD as SQL Server

    Encargado->>Pantalla: Abre el recibo y toca Anular
    Note over Pantalla: El botón solo aparece<br/>para encargados y dueños
    Pantalla-->>Encargado: Pide el motivo
    Encargado->>Pantalla: Escribe el motivo y confirma
    Pantalla->>Cliente: api POST /api/ventas/ID/anular/
    Cliente->>Permisos: POST con el token Bearer y el motivo
    Note over Permisos: Tiene que ser encargado o dueño.<br/>A un empleado le responde 403
    Permisos->>Vista: anular

    alt No se puede
        Note over Vista: Falta el motivo, la venta no existe<br/>o ya estaba anulada
        Vista-->>Pantalla: 400 o 404 con el mensaje
        Pantalla-->>Encargado: Muestra el mensaje
    else Se puede
        Note over Vista,BD: Una sola transacción
        Vista->>BD: SELECT con bloqueo de la venta
        Vista->>Reglas: devolver_al_stock
        Reglas->>BD: UPDATE producto e INSERT en movimiento_stock
        opt Era una venta fiada
            Vista->>BD: Baja la deuda del cliente
        end
        Vista->>BD: UPDATE venta, anulada con quién, cuándo y por qué
        Vista-->>Cliente: 200 con el recibo anulado
        Cliente-->>Pantalla: Recibo anulado
        Pantalla->>Cliente: Vuelve a pedir la lista
        Pantalla-->>Encargado: El recibo queda marcado como anulado
    end
```

El recibo anulado **sigue en la lista**, marcado, con quién lo anuló y por qué. La mercadería vuelve al stock.

## 4. Modificar una compra desde Recibos

Recibos no la modifica: manda a la pantalla Vender con ese recibo abierto.

```mermaid
sequenceDiagram
    actor Cajero
    participant Recibos as Pantalla Recibos (React)
    participant Vender as Pantalla Vender (React)
    participant Cliente as Cliente de la API (api.js)
    participant Vista as VentasViewSet
    participant BD as SQL Server

    Cajero->>Recibos: Abre el recibo y toca Modificar
    Note over Recibos: El botón aparece solo si el recibo<br/>dice que se puede modificar
    Recibos->>Vender: Va a /ventas con corregir igual al número del recibo
    Vender->>Cliente: api GET /api/ventas/ID/
    Cliente->>Vista: GET con el token Bearer
    Vista->>BD: SELECT de esa venta
    BD-->>Vista: Venta
    Vista-->>Vender: Recibo con sus productos

    alt Ya no se puede modificar
        Vender-->>Cajero: Avisa que está anulado, ya fue modificado<br/>o que le pida a un encargado
    else Se puede
        Vender-->>Cajero: Abre la compra con sus productos para cambiarla
        Note over Vender: Sigue como «Modificar una compra ya pagada»<br/>en diagrama-secuencia-ventas.md
    end
```

Un empleado que pide un recibo ajeno recibe «no existe» (404): no puede saber si esa venta existe.

## 5. La limpieza semanal del buzón

Nadie la pide: la hace el planificador, el mismo proceso del cierre de las 00:00.

```mermaid
sequenceDiagram
    participant Plan as Planificador (contenedor tareas)
    participant Servicios as Servicios de turnos
    participant ORM as Modelo Venta (ORM)
    participant BD as SQL Server

    loop Cada 20 segundos
        Plan->>Servicios: cerrar_dias_pendientes
        Servicios->>Servicios: limpiar_buzon, calcula el corte
        Note over Servicios: El corte es el domingo anterior<br/>al último domingo
        Servicios->>ORM: Sacar del buzón lo anterior al corte
        ORM->>BD: UPDATE venta, en_buzon pasa a falso
        Note over BD: La venta no se borra.<br/>Solo deja de aparecer en el buzón
    end
```

Como el corte se mueve una vez por semana, en el buzón siempre quedan a mano los recibos de esta semana y los de la anterior. El resto de los días la limpieza no encuentra nada para sacar. Las ventas viejas siguen en la base para el resumen, los cierres y los resultados; un dueño puede pedirlas todas con `GET /api/ventas/?todas=1`. La limpieza también corre en cada inicio de sesión, por si la computadora estuvo apagada.

## Casos comunes

El token vencido está en [`diagrama-secuencia-usuarios.md`](diagrama-secuencia-usuarios.md); el turno cerrado y el detalle de cobrar, modificar y anular, en [`diagrama-secuencia-ventas.md`](diagrama-secuencia-ventas.md); el cierre de las 00:00, en [`diagrama-secuencia-resumen-cierre.md`](diagrama-secuencia-resumen-cierre.md).
