# Diagrama entidad-relación de la base de datos

Las tablas del Sistema de Mercado, sus campos y cómo se relacionan. Está hecho leyendo los modelos reales de Django (`backend/*/models.py`), que son los que crean las tablas en SQL Server. Son **21 tablas** propias, repartidas en 7 aplicaciones.

El detalle campo por campo con los tipos de SQL Server de las tablas más viejas está en [`documentacion.md`](documentacion.md), sección 7.

## Cómo leer los diagramas

- Cada caja es una **tabla**. Adentro, cada renglón es un campo: tipo, nombre y, si corresponde, una marca.
- **PK** es la clave primaria (el identificador de la fila). **FK** es una clave foránea (apunta a otra tabla). **UK** es un valor que no se puede repetir.
- Las líneas son las **relaciones**. Los extremos dicen cuántos puede haber:

| Símbolo | Significa |
| --- | --- |
| `\|\|` | exactamente uno |
| `\|o` | cero o uno (el dato puede faltar) |
| `o{` | cero, uno o muchos |
| `\|{` | uno o muchos |

Por ejemplo, `SECCION ||--o{ CATEGORIA` se lee: una sección tiene muchas categorías (o ninguna), y cada categoría pertenece a exactamente una sección.

Tipos usados en los diagramas: `int` y `bigint` (números enteros), `string` (texto), `decimal` (números con decimales exactos, para plata y cantidades), `bool` (sí o no), `datetime` (fecha y hora) y `date` (solo fecha).

## 1. Vista general

Todas las tablas y las relaciones principales, sin los campos.

Para que se pueda leer, este diagrama **no dibuja** dos relaciones que tiene casi toda tabla: quién hizo la operación (`usuario`) y en qué turno (`turno`). Están listadas en la tabla «Quién y cuándo», más abajo.

```mermaid
erDiagram
    ROL ||--o{ USUARIO : "tiene"
    USUARIO ||--o{ TURNO : "trabaja"
    USUARIO ||--o{ REGISTRO_ACCESO : "genera"
    USUARIO ||--o{ CAMBIO_USUARIO : "recibe"

    SECCION ||--o{ CATEGORIA : "contiene"
    CATEGORIA ||--o{ PRODUCTO : "agrupa"
    PRODUCTO ||--o{ MOVIMIENTO_STOCK : "registra"
    PRODUCTO ||--o{ CAMBIO_PRODUCTO : "registra"

    VENTA ||--|{ DETALLE_VENTA : "incluye"
    PRODUCTO ||--o{ DETALLE_VENTA : "se vende en"
    VENTA |o--o{ VENTA : "corrige a"

    CLIENTE |o--o{ VENTA : "compra fiado"
    CLIENTE ||--o{ MOVIMIENTO_CUENTA : "registra"
    CLIENTE |o--o{ CAMBIO_CLIENTE : "registra"
    VENTA |o--o{ MOVIMIENTO_CUENTA : "origina"

    COMERCIANTE ||--o{ COMPRA : "vende"
    PRODUCTO ||--o{ COMPRA : "se compra en"
    COMPRA ||--o{ PAGO_COMPRA : "recibe"

    GASTO
    CIERRE_DIARIO
    CONFIGURACION_CUENTAS
    TOKEN_INVALIDADO
```

Las cuatro tablas sueltas del final no dependen de otra tabla de negocio:

- **`GASTO`** solo se relaciona con quién lo anotó y en qué turno.
- **`CIERRE_DIARIO`** es la foto de los totales de cada día: guarda números, no referencias.
- **`CONFIGURACION_CUENTAS`** tiene una sola fila, con el límite general de fiado.
- **`TOKEN_INVALIDADO`** guarda las sesiones que ya se cerraron.

## 2. Acceso, usuarios y turnos

Aplicaciones `usuarios` y `turnos`.

```mermaid
erDiagram
    ROL ||--o{ USUARIO : "tiene"
    USUARIO |o--o{ USUARIO : "fue creado por"
    USUARIO ||--o{ CAMBIO_USUARIO : "recibe el cambio"
    USUARIO ||--o{ CAMBIO_USUARIO : "hace el cambio"
    USUARIO |o--o{ REGISTRO_ACCESO : "genera"
    USUARIO ||--o{ TURNO : "trabaja"
    USUARIO |o--o{ TURNO : "corrige"

    ROL {
        int id PK
        string nombre UK "Administrador, Encargado o Empleado"
        string descripcion
    }
    USUARIO {
        int id PK
        string nombre_usuario UK
        string password "cifrada"
        string nombre
        string apellido
        string dni UK
        string email
        int rol_id FK
        bool activo "falso si fue dado de baja"
        bool debe_cambiar_password
        bool puede_gestionar_clientes
        bool is_superuser "verdadero para los dueños"
        int intentos_fallidos
        datetime bloqueado_hasta
        datetime fecha_creacion
        int creado_por_id FK
        datetime ultimo_acceso
    }
    CAMBIO_USUARIO {
        bigint id PK
        int usuario_id FK "a quién se le hizo"
        int realizado_por_id FK "quién lo hizo"
        string accion "ALTA, BAJA, REACTIVACION o PERMISO"
        string detalle
        datetime fecha_hora
    }
    REGISTRO_ACCESO {
        bigint id PK
        int usuario_id FK
        string nombre_usuario_ingresado
        string tipo "ingreso, salida, bloqueo"
        bool exitoso
        string ip
        string dispositivo
        datetime fecha_hora
    }
    TOKEN_INVALIDADO {
        int id PK
        string jti UK "identificador del token"
        datetime vence
        datetime fecha_hora
    }
    TURNO {
        bigint id PK
        int usuario_id FK
        datetime inicio
        datetime fin "vacío si sigue abierto"
        datetime ultima_actividad
        string tipo_cierre "USUARIO, INACTIVIDAD, SISTEMA o ADMINISTRADOR"
        bool para_revisar
        datetime fin_original
        int corregido_por_id FK
        datetime corregido_en
        string nota
    }
```

- `REGISTRO_ACCESO.usuario_id` puede estar vacío: se anotan también los intentos con un nombre de usuario que no existe.
- Las horas trabajadas no se guardan: se calculan como `fin` menos `inicio`.
- `TOKEN_INVALIDADO` no tiene relación con `USUARIO`: guarda solo el identificador del token.

## 3. Productos y stock

Aplicación `productos`.

```mermaid
erDiagram
    SECCION ||--o{ CATEGORIA : "contiene"
    CATEGORIA ||--o{ PRODUCTO : "agrupa"
    PRODUCTO ||--o{ MOVIMIENTO_STOCK : "registra"
    PRODUCTO ||--o{ CAMBIO_PRODUCTO : "registra"
    USUARIO ||--o{ PRODUCTO : "crea"
    USUARIO ||--o{ MOVIMIENTO_STOCK : "hace"
    USUARIO ||--o{ CAMBIO_PRODUCTO : "hace"
    TURNO |o--o{ MOVIMIENTO_STOCK : "durante"

    SECCION {
        int id PK
        string nombre UK "Almacén, Carnicería o Verdulería"
        int orden
    }
    CATEGORIA {
        int id PK
        int seccion_id FK
        string nombre "única dentro de la sección"
    }
    PRODUCTO {
        int id PK
        int categoria_id FK
        string nombre
        string codigo "número de producto, único si tiene"
        string codigo_barras "único si tiene"
        string unidad "UNIDAD o KG"
        decimal precio_venta
        decimal precio_costo
        string presentacion "SUELTO, CAJA, CAJON, BANDEJA, BOLSA, PACK o BULTO"
        decimal contenido "lo que trae cada caja o cajón"
        decimal stock_actual "solo cambia con movimientos"
        decimal stock_minimo
        bool activo "falso si fue dado de baja"
        datetime fecha_creacion
        int creado_por_id FK
    }
    MOVIMIENTO_STOCK {
        bigint id PK
        int producto_id FK
        string tipo "INGRESO, PERDIDA, AJUSTE o VENTA"
        decimal cantidad "con signo, positivo entra"
        decimal stock_resultante
        decimal costo_unitario
        string motivo
        int usuario_id FK
        bigint turno_id FK
        datetime fecha_hora
    }
    CAMBIO_PRODUCTO {
        bigint id PK
        int producto_id FK
        int realizado_por_id FK
        string accion "ALTA, BAJA, REACTIVACION, EDICION o PRECIO"
        string detalle
        datetime fecha_hora
    }
    USUARIO {
        int id PK
    }
    TURNO {
        bigint id PK
    }
```

- La **sección** de un producto no está en el producto: se llega a través de su categoría.
- `PRODUCTO.stock_actual` se guarda para que el semáforo sea rápido, pero cada cambio queda respaldado por una fila de `MOVIMIENTO_STOCK`.
- `turno_id` está vacío cuando la operación la hizo un dueño, porque los dueños no llevan turno. Vale lo mismo en todas las tablas que tienen ese campo.

## 4. Ventas y cuentas corrientes

Aplicaciones `ventas` y `clientes`.

```mermaid
erDiagram
    VENTA ||--|{ DETALLE_VENTA : "incluye"
    PRODUCTO ||--o{ DETALLE_VENTA : "se vende en"
    VENTA |o--o{ VENTA : "corrige a"
    CLIENTE |o--o{ VENTA : "compra fiado"
    CLIENTE ||--o{ MOVIMIENTO_CUENTA : "registra"
    VENTA |o--o{ MOVIMIENTO_CUENTA : "origina"
    CLIENTE |o--o{ CAMBIO_CLIENTE : "registra"
    USUARIO ||--o{ VENTA : "cobra"
    USUARIO |o--o{ VENTA : "anula"
    TURNO |o--o{ VENTA : "durante"
    USUARIO ||--o{ CLIENTE : "crea"
    USUARIO ||--o{ MOVIMIENTO_CUENTA : "hace"
    TURNO |o--o{ MOVIMIENTO_CUENTA : "durante"
    USUARIO ||--o{ CAMBIO_CLIENTE : "hace"

    VENTA {
        bigint id PK "también es el número de recibo"
        int usuario_id FK "quién la cobró"
        bigint turno_id FK
        datetime fecha_hora
        string medio_pago "EFECTIVO, DEBITO, CREDITO, TRANSFERENCIA, QR o CUENTA"
        decimal total
        decimal paga_con
        decimal vuelto
        int cliente_id FK "solo si fue fiada"
        bool en_buzon "si sigue en el buzón de recibos"
        bigint corrige_a_id FK "la venta que reemplaza"
        bool anulada
        int anulada_por_id FK
        datetime anulada_en
        string motivo_anulacion
    }
    DETALLE_VENTA {
        bigint id PK
        bigint venta_id FK
        int producto_id FK
        string nombre "como era al vender"
        string unidad
        decimal cantidad
        decimal precio_unitario "precio de ese momento"
        decimal costo_unitario "costo de ese momento"
        decimal subtotal
    }
    CLIENTE {
        int id PK
        string nombre UK
        string dni
        string telefono
        string direccion
        string nota
        decimal limite "propio, vacío usa el general"
        decimal saldo "lo que debe, solo cambia con movimientos"
        bool activo
        datetime fecha_creacion
        int creado_por_id FK
    }
    MOVIMIENTO_CUENTA {
        bigint id PK "número del comprobante de pago"
        int cliente_id FK
        string tipo "COMPRA, PAGO, ANULACION o AJUSTE"
        decimal importe "con signo, positivo sube la deuda"
        decimal saldo_resultante
        bigint venta_id FK
        string medio_pago "solo en los pagos"
        string detalle
        int usuario_id FK
        bigint turno_id FK
        datetime fecha_hora
    }
    CAMBIO_CLIENTE {
        bigint id PK
        int cliente_id FK "vacío si cambió el límite general"
        int realizado_por_id FK
        string accion "ALTA, BAJA, REACTIVACION, EDICION, LIMITE o LIMITE_GENERAL"
        string detalle
        datetime fecha_hora
    }
    CONFIGURACION_CUENTAS {
        int id PK "una sola fila"
        decimal limite_general "vacío es sin límite"
    }
    PRODUCTO {
        int id PK
    }
    USUARIO {
        int id PK
    }
    TURNO {
        bigint id PK
    }
```

- Una venta tiene **uno o más** renglones (`DETALLE_VENTA`); es la única relación «uno o muchos» obligatoria del sistema.
- `DETALLE_VENTA` copia el nombre, el precio y el costo del producto al momento de vender. Por eso, aunque después cambie el producto, los recibos y las ganancias anteriores no cambian.
- `VENTA.corrige_a_id` apunta a **otra venta**: cuando se modifica una compra ya pagada, la nueva guarda cuál era la original.
- La deuda del cliente (`CLIENTE.saldo`) funciona como el stock: cada cambio tiene su fila en `MOVIMIENTO_CUENTA`.

## 5. Compras a comerciantes, gastos y cierre del día

Aplicaciones `compras`, `gastos` y `turnos`.

```mermaid
erDiagram
    COMERCIANTE ||--o{ COMPRA : "vende"
    PRODUCTO ||--o{ COMPRA : "se compra en"
    COMPRA ||--o{ PAGO_COMPRA : "recibe"
    USUARIO ||--o{ COMERCIANTE : "crea"
    USUARIO ||--o{ COMPRA : "anota"
    USUARIO |o--o{ COMPRA : "anula"
    TURNO |o--o{ COMPRA : "durante"
    USUARIO ||--o{ PAGO_COMPRA : "anota"
    TURNO |o--o{ PAGO_COMPRA : "durante"
    USUARIO ||--o{ GASTO : "anota"
    USUARIO |o--o{ GASTO : "anula"
    TURNO |o--o{ GASTO : "durante"

    COMERCIANTE {
        int id PK
        string nombre UK
        datetime fecha_creacion
        int creado_por_id FK
    }
    COMPRA {
        bigint id PK
        int comerciante_id FK
        int producto_id FK
        string nombre_producto "como era al comprar"
        string unidad
        decimal cantidad "total en kilos o unidades"
        string presentacion "en qué se compró"
        decimal bultos "cuántas cajas o cajones"
        decimal contenido "cuánto trae cada uno"
        decimal costo_total
        decimal costo_unitario
        decimal pagado "solo cambia con pagos"
        bool sumo_stock
        string nota
        int usuario_id FK
        bigint turno_id FK
        datetime fecha_hora "la pone el sistema"
        bool anulada
        int anulada_por_id FK
        datetime anulada_en
        string motivo_anulacion
    }
    PAGO_COMPRA {
        bigint id PK
        bigint compra_id FK
        decimal importe
        string medio_pago
        int usuario_id FK
        bigint turno_id FK
        datetime fecha_hora
    }
    GASTO {
        bigint id PK
        decimal monto "en positivo, se resta en las cuentas"
        string proposito
        int usuario_id FK
        bigint turno_id FK
        datetime fecha_hora
        bool anulado
        int anulado_por_id FK
        datetime anulado_en
        string motivo_anulacion
    }
    CIERRE_DIARIO {
        bigint id PK
        date fecha UK "un cierre por día"
        datetime generado_en
        int turnos
        int minutos_trabajados
        int turnos_cerrados_por_sistema
        int movimientos_stock
        decimal valor_ingresado
        decimal valor_perdidas
        decimal valor_ajustes
        int cambios
        int ventas_cantidad
        decimal ventas_total
        decimal ventas_efectivo
        decimal ventas_fiado
        decimal cobros_cuenta
        decimal cobros_cuenta_efectivo
        int gastos_cantidad
        decimal gastos_total
        decimal compras_total
        decimal pagos_comerciantes
        decimal pagos_comerciantes_efectivo
        decimal ganancia_bruta
    }
    PRODUCTO {
        int id PK
    }
    USUARIO {
        int id PK
    }
    TURNO {
        bigint id PK
    }
```

- El **estado del pago** de una compra (pagado, falta una parte, sin pagar) no es un campo: se calcula comparando `pagado` con `costo_total`.
- `CIERRE_DIARIO` no tiene claves foráneas a propósito. Guarda los totales del día como quedaron a las 00:00; la plata que entró, la cuenta final y el efectivo esperado se calculan con esos números.

## Quién y cuándo

Casi todas las tablas guardan quién hizo la operación y, si corresponde, en qué turno. Son las relaciones que la vista general no dibuja.

| Tabla | Quién (apunta a `usuario`) | Turno (apunta a `turno`) |
| --- | --- | --- |
| `usuario` | `creado_por_id` | — |
| `cambio_usuario` | `realizado_por_id` | — |
| `turno` | `usuario_id`, `corregido_por_id` | — |
| `producto` | `creado_por_id` | — |
| `movimiento_stock` | `usuario_id` | `turno_id` |
| `cambio_producto` | `realizado_por_id` | — |
| `venta` | `usuario_id`, `anulada_por_id` | `turno_id` |
| `cliente` | `creado_por_id` | — |
| `movimiento_cuenta` | `usuario_id` | `turno_id` |
| `cambio_cliente` | `realizado_por_id` | — |
| `comerciante` | `creado_por_id` | — |
| `compra` | `usuario_id`, `anulada_por_id` | `turno_id` |
| `pago_compra` | `usuario_id` | `turno_id` |
| `gasto` | `usuario_id`, `anulado_por_id` | `turno_id` |

## Reglas que el diagrama no muestra

- **Nada se borra.** Usuarios, productos y clientes tienen `activo`; ventas, compras y gastos tienen `anulada` o `anulado`. Casi todas las claves foráneas están protegidas: la base no deja borrar una fila que otra está usando. La principal excepción son los renglones de una venta, que dependen de ella.
- **Plata y cantidades son `decimal`, nunca números con coma flotante**, para que las cuentas den exactas. La plata usa 2 decimales y las cantidades 3 (gramos).
- **Tablas de historial de solo lectura:** `cambio_usuario`, `cambio_producto`, `cambio_cliente`, `registro_acceso`, `movimiento_stock`, `movimiento_cuenta` y `pago_compra` no se modifican ni se borran desde el sistema.
- **Únicos con condición:** en `producto`, el número de producto y el código de barras son únicos solo cuando tienen valor. En `categoria`, el nombre es único dentro de su sección.
- **Tablas que no están acá:** Django crea además algunas tablas propias (permisos, sesiones del panel `/admin/`, registro de migraciones). No forman parte del modelo del negocio.
