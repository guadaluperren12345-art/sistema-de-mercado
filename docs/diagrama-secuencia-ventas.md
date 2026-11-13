# Diagramas de secuencia: módulo Vender

Cómo viaja un pedido entre las capas del sistema cuando alguien **arma y cobra una venta**, la **anota en cuenta corriente**, **modifica una compra ya pagada** o la **anula**. Están hechos a partir del código real (`frontend/src/paginas/Venta.jsx`, `Recibos.jsx`, `frontend/src/api.js`, `frontend/src/dispositivos.js`, `backend/ventas/api.py`, `backend/clientes/servicios.py` y `backend/turnos/autenticacion.py`).

## Las capas

| Capa | Qué es | Archivos |
| --- | --- | --- |
| Pantalla | Lo que ve el cajero en el navegador (React) | `Venta.jsx`, `Recibos.jsx`, `Recibo.jsx` |
| Lector e impresora | El lector escribe como un teclado; el recibo sale por la impresión del navegador | `dispositivos.js` |
| Cliente de la API | Agrega el token a cada pedido y lo renueva si venció | `api.js` |
| Proxy de Vite | Recibe `/api/...` en el puerto 5173 y lo pasa al backend | `vite.config.js` |
| Autenticación y turno | Verifica quién es y que tenga su turno abierto | `AutenticacionConTurno`, `PasswordAlDia` |
| Vista | Recibe el pedido y coordina | `VentasViewSet` |
| Serializer | Valida los datos y arma el recibo | `NuevaVentaSerializer`, `VentaSerializer` |
| Reglas de venta | Calculan el total, descuentan stock y anotan la deuda | `cobrar`, `bloquear_productos`, `mover_stock`, `devolver_al_stock` y `clientes/servicios.py` |
| Modelos (ORM) | Convierten los objetos en consultas SQL | `Venta`, `DetalleVenta`, `Producto`, `MovimientoStock`, `Cliente`, `MovimientoCuenta` |
| Base de datos | SQL Server | tablas `venta`, `detalle_venta`, `producto`, `movimiento_stock`, `cliente`, `movimiento_cuenta` |

Quién puede hacer cada cosa:

| Operación | Quién |
| --- | --- |
| Vender | Todos (dueño, encargado, empleado) |
| Vender en cuenta corriente | Todos, a un cliente ya cargado |
| Modificar una compra pagada | El cajero que la cobró, el mismo día; encargados y dueños, cualquiera |
| Anular una venta | Encargados y dueños |

## 1. Armar la venta en la pantalla

Mientras se cargan los productos no se guarda nada: todo pasa en el navegador. El servidor solo interviene al entrar (para traer los productos) y al cobrar.

```mermaid
sequenceDiagram
    actor Cajero
    participant Lector as Lector de códigos
    participant Pantalla as Pantalla Vender (React)
    participant Cliente as Cliente de la API (api.js)
    participant API as Backend (Django)
    participant BD as SQL Server

    Cajero->>Pantalla: Abre Vender
    Pantalla->>Cliente: api GET /api/productos/ con activo=1
    Cliente->>API: Pedido con el token Bearer
    API->>BD: SELECT de los productos a la venta
    BD-->>API: Productos con precio y stock
    API-->>Pantalla: Lista de productos
    Pantalla->>Cliente: api GET /api/clientes/ con activo=1
    Cliente->>API: Pedido con el token Bearer
    API-->>Pantalla: Clientes de cuenta corriente

    loop Por cada producto
        alt Con el lector
            Cajero->>Lector: Escanea el código de barras
            Lector->>Pantalla: Escribe el código y Enter
        else A mano
            Cajero->>Pantalla: Escribe el número o el nombre
        end
        Pantalla->>Pantalla: Busca el producto en la lista<br/>y lo suma al carrito
        opt Se vende por kilo
            Cajero->>Pantalla: Escribe el peso
        end
        Pantalla-->>Cajero: Muestra el total en grande
    end
    Note over Pantalla: Las cantidades se pueden cambiar<br/>o quitar antes de cobrar
```

El precio que se ve en pantalla es solo para mostrar: al cobrar, el servidor vuelve a tomar el precio de la base.

## 2. Cobrar la venta

```mermaid
sequenceDiagram
    actor Cajero
    participant Pantalla as Pantalla Vender (React)
    participant Cliente as Cliente de la API (api.js)
    participant Proxy as Proxy de Vite
    participant Auth as Autenticación y turno
    participant Vista as VentasViewSet
    participant Ser as NuevaVentaSerializer
    participant Reglas as Reglas de venta (cobrar)
    participant ORM as Modelos (ORM)
    participant BD as SQL Server

    Cajero->>Pantalla: Elige cómo paga y toca Cobrar
    Pantalla->>Pantalla: Revisa cantidades y el vuelto
    Pantalla->>Cliente: api POST /api/ventas/
    Cliente->>Proxy: POST con items, medio de pago y paga con
    Proxy->>Auth: Pasa el pedido al backend
    Auth->>BD: Busca al usuario y su turno abierto
    BD-->>Auth: Usuario y turno
    Note over Auth: Empleados y encargados necesitan<br/>el turno abierto. Los dueños no llevan turno
    Auth->>Vista: create
    Vista->>Ser: Validar items y medio de pago
    Ser-->>Vista: Datos válidos

    Note over Vista,BD: Una sola transacción
    Vista->>Reglas: bloquear_productos
    Reglas->>BD: SELECT con bloqueo de esos productos
    BD-->>Reglas: Productos bloqueados
    Vista->>Reglas: cobrar
    Note over Reglas: Controla que estén a la venta y las cantidades.<br/>Calcula el total con el precio de la base

    alt Algo no se puede vender
        Reglas-->>Vista: Error de venta
        Vista-->>Pantalla: 400 con el mensaje
        Pantalla-->>Cajero: Muestra qué pasó
    else Todo bien
        Reglas->>ORM: Crear la venta
        ORM->>BD: INSERT en venta
        loop Por cada producto
            Reglas->>ORM: Crear el renglón con precio<br/>y costo del momento
            ORM->>BD: INSERT en detalle_venta
            Reglas->>ORM: Descontar del stock
            ORM->>BD: UPDATE producto e INSERT en movimiento_stock
        end
        Reglas-->>Vista: Venta y avisos de stock
        Vista-->>Proxy: 201 con el recibo
        Proxy-->>Cliente: 201
        Cliente-->>Pantalla: Recibo
        Pantalla-->>Cajero: Venta cobrada, total y vuelto
        opt Imprimir
            Pantalla->>Pantalla: Impresión del navegador,<br/>recibo de 58 u 80 mm
        end
    end
```

Puntos a tener en cuenta:

- **Bloqueo de productos:** se bloquean siempre en el mismo orden para que dos cajas vendiendo a la vez no pisen el stock.
- **Vender sin stock:** se permite. El stock queda en negativo y el recibo vuelve con un aviso para que alguien haga un recuento.
- **Precio y costo del momento:** cada renglón guarda el precio y el costo que tenía el producto al cobrar. Si después cambia el precio, los recibos y las ganancias anteriores no cambian.
- **El recibo siempre queda guardado**, se imprima o no.

## 3. Vender en cuenta corriente (fiado)

Es el mismo camino que cobrar, con dos pasos más: se elige el cliente y se controla su límite.

```mermaid
sequenceDiagram
    actor Cajero
    participant Pantalla as Pantalla Vender (React)
    participant Vista as VentasViewSet
    participant Reglas as Reglas de venta (cobrar)
    participant Cuentas as Reglas de cuenta corriente
    participant BD as SQL Server

    Cajero->>Pantalla: Elige Cuenta corriente y el cliente
    Pantalla-->>Cajero: Muestra cuánto debe y cuánto le queda
    Cajero->>Pantalla: Toca Anotar en la cuenta
    Pantalla->>Vista: POST /api/ventas/ con medio CUENTA y el cliente
    Note over Pantalla,Vista: Pasa por el cliente de la API, el proxy<br/>y la autenticación, igual que al cobrar

    Note over Vista,BD: Una sola transacción
    Vista->>Reglas: bloquear_productos y cobrar
    Reglas->>Cuentas: cliente_para_fiar con el total
    Cuentas->>BD: SELECT con bloqueo del cliente
    BD-->>Cuentas: Cliente y su deuda
    Note over Cuentas: El límite es el propio del cliente<br/>o, si no tiene, el general

    alt No se le puede fiar
        Note over Cuentas: No se eligió cliente, está dado de baja<br/>o con esta compra pasa su límite
        Cuentas-->>Reglas: Error de cuenta
        Reglas-->>Vista: Error de venta
        Vista-->>Pantalla: 400 con el mensaje
        Pantalla-->>Cajero: Explica cuánto le queda para fiar
    else Se le puede fiar
        Reglas->>BD: INSERT en venta con el cliente
        Reglas->>BD: Renglones y descuento de stock
        Reglas->>Cuentas: anotar_compra
        Cuentas->>BD: UPDATE cliente con la deuda nueva
        Cuentas->>BD: INSERT en movimiento_cuenta, tipo COMPRA
        Vista-->>Pantalla: 201 con el recibo a nombre del cliente
        Pantalla-->>Cajero: Anotado en la cuenta, no se cobra ahora
    end
```

Si el límite no alcanza, la venta entera se cancela: no se crea el recibo ni se descuenta stock.

## 4. Modificar una compra ya pagada

El cliente se olvidó algo, o quiere sacar o cambiar un producto. La venta original no se toca: queda anulada como «Compra modificada» y se crea una nueva enlazada.

```mermaid
sequenceDiagram
    actor Cajero
    participant Pantalla as Pantalla Vender (React)
    participant Vista as VentasViewSet
    participant Reglas as Reglas de venta
    participant Cuentas as Reglas de cuenta corriente
    participant BD as SQL Server

    Cajero->>Pantalla: Toca Modificar esta compra
    Pantalla->>Pantalla: Vuelve a abrir la compra con sus productos
    Cajero->>Pantalla: Agrega, saca o cambia productos
    Pantalla-->>Cajero: Muestra cuánto cobrar de más o devolver
    Cajero->>Pantalla: Toca Guardar la compra modificada
    Pantalla->>Vista: POST /api/ventas/ID/corregir/

    Note over Vista,BD: Una sola transacción
    Vista->>BD: SELECT con bloqueo de la venta original
    BD-->>Vista: Venta original

    alt No se puede modificar
        Note over Vista: No existe o es de otro cajero, ya estaba anulada,<br/>no es de hoy, o no se cambió nada
        Vista-->>Pantalla: 400 o 404 con el mensaje
        Pantalla-->>Cajero: Muestra el mensaje
    else Se puede
        Vista->>Reglas: bloquear_productos, los de antes y los nuevos
        Vista->>Reglas: devolver_al_stock
        Reglas->>BD: Devuelve la mercadería de la venta original
        opt La original era fiada
            Vista->>Cuentas: deshacer_compra
            Cuentas->>BD: Baja la deuda e INSERT en movimiento_cuenta, tipo ANULACION
        end
        Vista->>Reglas: cobrar la versión corregida
        Reglas->>BD: Venta nueva enlazada con corrige_a,<br/>renglones y descuento de stock
        Vista->>BD: UPDATE de la original, anulada<br/>con motivo Compra modificada
        Vista-->>Pantalla: 201 con el recibo nuevo
        Pantalla-->>Cajero: Cobrale la diferencia o devolvele
    end
```

Los totales del día cuentan solo la versión corregida. En la Actividad del sistema aparece como «Compra modificada», con el recibo que reemplaza y cómo cambió el total.

## 5. Anular una venta

Devolver la compra entera. Solo encargados y dueños, desde Recibos.

```mermaid
sequenceDiagram
    actor Encargado
    participant Pantalla as Pantalla Recibos (React)
    participant Permisos as Autenticación y permisos
    participant Vista as VentasViewSet
    participant Reglas as Reglas de venta
    participant Cuentas as Reglas de cuenta corriente
    participant BD as SQL Server

    Encargado->>Pantalla: Toca Anular y escribe el motivo
    Pantalla->>Permisos: POST /api/ventas/ID/anular/
    Note over Permisos: Tiene que ser encargado o dueño.<br/>A un empleado le responde 403

    alt Falta el motivo
        Permisos->>Vista: anular
        Vista-->>Pantalla: 400, indicá el motivo
    else Con motivo
        Permisos->>Vista: anular
        Note over Vista,BD: Una sola transacción
        Vista->>BD: SELECT con bloqueo de la venta
        BD-->>Vista: Venta
        alt No existe o ya estaba anulada
            Vista-->>Pantalla: 404 o 400 con el mensaje
        else Se puede anular
            Vista->>Reglas: bloquear_productos y devolver_al_stock
            Reglas->>BD: UPDATE producto e INSERT en movimiento_stock,<br/>al costo que tenía cuando se vendió
            opt Era una venta fiada
                Vista->>Cuentas: deshacer_compra
                Cuentas->>BD: Baja la deuda del cliente
            end
            Vista->>BD: UPDATE venta, anulada con quién, cuándo y por qué
            Vista-->>Pantalla: 200 con el recibo anulado
            Pantalla-->>Encargado: El recibo queda marcado como anulado
        end
    end
```

La venta **no se borra**: queda guardada con quién la anuló, cuándo y el motivo, y deja de sumar en los totales.

## Qué pasa si el turno se cerró

Un empleado o encargado solo puede vender con su turno abierto. Si el sistema lo cerró a las 00:00, o se cerró sesión en otro equipo, el próximo pedido se rechaza:

```mermaid
sequenceDiagram
    actor Cajero
    participant Pantalla as Pantalla Vender (React)
    participant Cliente as Cliente de la API (api.js)
    participant Auth as Autenticación y turno
    participant BD as SQL Server

    Cajero->>Pantalla: Toca Cobrar
    Pantalla->>Cliente: api POST /api/ventas/
    Cliente->>Auth: Pedido con el token Bearer
    Auth->>BD: Busca el turno abierto del usuario
    BD-->>Auth: No tiene turno abierto
    Auth-->>Cliente: 401, tu turno terminó
    Cliente-->>Pantalla: Avisa que la sesión terminó
    Pantalla-->>Cajero: Vuelve al inicio de sesión<br/>y explica por qué
```

El caso del token vencido (se renueva solo y se repite el pedido) está en [`diagrama-secuencia-usuarios.md`](diagrama-secuencia-usuarios.md) y funciona igual acá.
