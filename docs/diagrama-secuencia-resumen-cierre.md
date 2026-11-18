# Diagramas de secuencia: resumen y cierre del día

Cómo viaja un pedido entre las capas del sistema cuando un dueño **consulta el resumen** de un período o **la lista de cierres**, y cómo el sistema **hace solo el cierre del día a las 00:45 y les avisa a los dueños**. Están hechos a partir del código real (`frontend/src/paginas/Resumen.jsx`, `frontend/src/useConsulta.js`, `frontend/src/api.js`, `backend/turnos/api.py`, `backend/turnos/servicios.py`, `backend/turnos/management/commands/planificador.py` y `backend/usuarios/views.py`).

## Las capas

| Capa | Qué es | Archivos |
| --- | --- | --- |
| Pantalla | Lo que ve el dueño en el navegador (React) | `Resumen.jsx`, `SelectorPeriodo.jsx` |
| Cliente de la API | Agrega el token a cada pedido y lo renueva si venció | `useConsulta.js`, `api.js` |
| Proxy de Vite | Recibe `/api/...` en el puerto 5173 y lo pasa al backend | `vite.config.js` |
| Autenticación y permisos | Verifica quién es y que sea dueño | `AutenticacionConTurno`, `EsAdministrador`, `PasswordAlDia` |
| Vista | Recibe el pedido y coordina | `ResumenView`, `CierresView` |
| Servicios | Hacen las cuentas y el cierre | `resumen`, `cuenta_final`, `cerrar_dias_pendientes`, `generar_cierre`, `limpiar_buzon` |
| Planificador | Proceso aparte que revisa cada 20 segundos si terminó el día | contenedor `tareas`, `planificador.py` |
| Modelos (ORM) | Convierten los objetos en consultas SQL | `Venta`, `DetalleVenta`, `MovimientoStock`, `Turno`, `Gasto`, `Compra`, `PagoCompra`, `MovimientoCuenta`, `CierreDiario` |
| Base de datos | SQL Server | las tablas de esos modelos |

Todo este módulo es **solo para dueños**. Un encargado o un empleado reciben un error 403 antes de llegar a la vista.

Este módulo casi no guarda nada propio: **lee** lo que dejaron los demás (ventas, stock, gastos, compras, cuentas corrientes y turnos) y hace las cuentas. Lo único que escribe es la fila del cierre de cada día.

## 1. Obtención: ver el resumen de un período

```mermaid
sequenceDiagram
    actor Dueno as Dueño
    participant Pantalla as Pantalla Resumen (React)
    participant Cliente as Cliente de la API (api.js)
    participant Proxy as Proxy de Vite
    participant Permisos as Autenticación y permisos
    participant Vista as ResumenView
    participant Servicios as Servicios de turnos
    participant ORM as Modelos (ORM)
    participant BD as SQL Server

    Dueno->>Pantalla: Abre Resumen o elige día, semana o mes
    Pantalla->>Cliente: api GET /api/resumen/ con desde y hasta
    Cliente->>Proxy: GET con el token Bearer
    Proxy->>Permisos: Pasa el pedido al backend
    Note over Permisos: Token válido y es Administrador
    Permisos->>Vista: get
    Vista->>Servicios: cerrar_dias_pendientes
    Note over Servicios: Si quedó algún día sin cerrar, lo cierra ahora.<br/>Ver el diagrama 3
    Vista->>Vista: Lee las fechas

    alt Fechas mal escritas o más de 3 meses
        Vista-->>Pantalla: 400 con el mensaje
        Pantalla-->>Dueno: Muestra el error
    else Fechas correctas
        Vista->>Servicios: resumen de ese período
        Servicios->>ORM: Movimientos de stock del período
        ORM->>BD: SELECT en movimiento_stock
        BD-->>Servicios: Lo que entró, se perdió y se ajustó
        Servicios->>ORM: Turnos del período
        ORM->>BD: SELECT en turno
        BD-->>Servicios: Horas trabajadas por persona
        Servicios->>ORM: Ventas y sus renglones
        ORM->>BD: SELECT en venta y detalle_venta
        BD-->>Servicios: Vendido, por medio de pago y por sección
        Servicios->>ORM: Pagos de cuentas corrientes, gastos,<br/>compras y pagos a comerciantes
        ORM->>BD: SELECT en movimiento_cuenta, gasto,<br/>compra y pago_compra
        BD-->>Servicios: Plata que entró y que salió
        Note over Servicios: cuenta_final<br/>plata que entró menos gastos<br/>menos pagos a comerciantes
        Servicios-->>Vista: Resumen completo
        Vista-->>Proxy: 200 con el resumen
        Proxy-->>Cliente: 200
        Cliente-->>Pantalla: Resumen
        Pantalla-->>Dueno: Cuenta final arriba, tarjetas y tablas
    end
```

Qué trae el resumen:

- **`caja`:** plata que entró, gastos, pagos a comerciantes, cuenta final y efectivo que debería haber.
- **`ventas`:** cantidad, total, por medio de pago, por sección, lo vendido fiado y la ganancia bruta.
- **`cuenta_corriente`**, **`gastos`** y **`comerciantes`:** los pagos de clientes, la lista de gastos y las compras y pagos a comerciantes.
- **`mercaderia`** y **`personal`:** lo que entró y salió del stock, y las horas trabajadas.
- **`por_dia`:** los mismos totales día por día, para la semana y el mes.

La cuenta final se arma así: lo vendido, menos lo fiado (no entró plata), más los pagos de cuentas corrientes; a eso se le restan los gastos y lo pagado a comerciantes. Las ventas anuladas y los gastos anulados no cuentan.

## 2. Obtención: ver los cierres automáticos

Al abrir la pantalla se hace este pedido junto con el del resumen.

```mermaid
sequenceDiagram
    actor Dueno as Dueño
    participant Pantalla as Pantalla Resumen (React)
    participant Cliente as Cliente de la API (api.js)
    participant Permisos as Autenticación y permisos
    participant Vista as CierresView
    participant Servicios as Servicios de turnos
    participant Ser as CierreDiarioSerializer
    participant BD as SQL Server

    Dueno->>Pantalla: Abre Resumen
    Pantalla->>Cliente: api GET /api/cierres/
    Cliente->>Permisos: GET con el token Bearer
    Note over Permisos: Token válido y es Administrador
    Permisos->>Vista: get
    Vista->>Servicios: cerrar_dias_pendientes
    Vista->>BD: SELECT de los últimos 60 cierres
    BD-->>Vista: Filas de cierre_diario
    Vista->>Ser: Convertir a JSON
    Note over Ser: Calcula plata que entró, cuenta final<br/>y efectivo esperado con lo guardado
    Ser-->>Vista: Cierres
    Vista-->>Cliente: 200 con la lista
    Cliente-->>Pantalla: Cierres
    Pantalla-->>Dueno: Tabla de cierres, uno por día
    opt Toca un día de la tabla
        Dueno->>Pantalla: Elige ese día
        Pantalla->>Cliente: api GET /api/resumen/ de ese día
        Note over Pantalla: Sigue como en el diagrama 1
    end
```

La diferencia entre las dos cosas: el **resumen** se calcula en el momento con los datos de ahora; el **cierre** es la foto que el sistema guardó de cada día cuando terminó.

## 3. El cierre automático de las 00:45 y el aviso a los dueños

Acá no interviene ninguna persona ni ninguna pantalla: lo dispara el planificador, un proceso que corre en su propio contenedor.

```mermaid
sequenceDiagram
    participant Plan as Planificador (contenedor tareas)
    participant Servicios as Servicios de turnos
    participant Avisos as Servicios de avisos
    participant ORM as Modelos (ORM)
    participant BD as SQL Server
    participant Afuera as Telegram y correo

    loop Cada 20 segundos
        Plan->>Servicios: cerrar_dias_pendientes
        Servicios->>ORM: limpiar_buzon
        ORM->>BD: UPDATE venta, salen del buzón los recibos<br/>anteriores al domingo de la semana pasada
        Note over Servicios: El corte se mueve cada domingo.<br/>El resto de la semana no encuentra nada para sacar
        Servicios->>BD: Busca la fecha del último cierre
        BD-->>Servicios: Lo que haya pendiente

        alt Todavía no terminó el día
            Servicios-->>Plan: Nada para hacer
        else Pasaron las 00:45
            Note over Servicios: No se le cierra la cuenta a nadie.<br/>Cada persona cierra la suya al irse

            loop Por cada día sin cerrar
                Servicios->>Servicios: generar_cierre, calcula el resumen de ese día
                Servicios->>BD: Lee ventas, stock, turnos, gastos,<br/>compras y cuentas corrientes
                BD-->>Servicios: Totales del día
                Servicios->>ORM: Guardar el cierre si no existe
                ORM->>BD: INSERT en cierre_diario
            end
            loop Por cada dueño activo
                Servicios->>Avisos: avisar_cierre, arma el texto con toda la caja del día
                Avisos->>BD: INSERT en notificacion, el aviso dentro del sistema,<br/>e INSERT en envio_notificacion para Telegram y para el correo
            end
            Servicios-->>Plan: Cierres generados
            Plan->>Plan: Anota en su registro qué día cerró
        end

        Plan->>Avisos: enviar_pendientes
        Avisos->>BD: Busca los envíos pendientes a los que ya les toca
        alt Hay internet
            Avisos->>Afuera: Mensaje del bot de Telegram y correo por SMTP
            Afuera-->>Avisos: Recibido
            Avisos->>BD: UPDATE envio_notificacion, enviado
        else No hay internet o falló
            Avisos->>BD: UPDATE envio_notificacion, suma un intento<br/>y lo deja para más tarde
        end
    end
```

Puntos a tener en cuenta:

- **El día del mercado va de 00:45 a 00:45.** Lo que se vende o se gasta antes de las 00:45 es del día anterior (`backend/core/dia.py`).
- **El sistema no le cierra la cuenta a nadie.** Cada empleado cierra la suya al irse; el aviso nombra a quienes siguen con la cuenta abierta.
- **El aviso sale por tres caminos:** dentro del sistema (pantalla «Avisos»), por Telegram y por correo. Si no hay internet, se reintenta solo durante varias horas. Un fallo al avisar nunca frena el cierre.
- **Los empleados no hacen el cierre.** Lo hace el sistema solo y el resultado lo ven únicamente los dueños.
- **No se duplica.** La fecha del cierre es única y se guarda solo si no existe, así que llamar a la función muchas veces no hace daño.
- **El buzón de recibos no borra ventas.** Solo dejan de aparecer en el buzón; siguen en la base para los reportes.
- **Qué guarda el cierre:** turnos y minutos trabajados, movimientos y valor de la mercadería, cambios registrados, ventas (total, efectivo y fiado), pagos de cuentas corrientes, gastos, compras y pagos a comerciantes, y la ganancia bruta.

## 4. Si la computadora estaba apagada a las 00:45

El planificador no pudo correr, así que el cierre se pone al día la próxima vez que alguien entra.

```mermaid
sequenceDiagram
    actor Persona as Cualquier usuario
    participant Pantalla as Pantalla de ingreso (React)
    participant Vista as LoginView
    participant Servicios as Servicios de turnos
    participant BD as SQL Server

    Persona->>Pantalla: Escribe usuario y contraseña
    Pantalla->>Vista: POST /api/auth/login/
    Vista->>BD: Verifica la contraseña
    BD-->>Vista: Correcta
    Vista->>Servicios: cerrar_dias_pendientes
    Note over Servicios: Hace lo mismo que el diagrama 3,<br/>un cierre por cada día que faltaba, hasta un año atrás
    Servicios->>BD: INSERT en cierre_diario y los avisos para los dueños
    Vista->>Servicios: abrir_turno
    Servicios->>BD: INSERT en turno
    Note over Servicios: Solo empleados y encargados.<br/>Los dueños no llevan turno
    Vista-->>Pantalla: 200 con los tokens y el usuario
    Pantalla-->>Persona: Entra al sistema
```

La misma puesta al día ocurre también al pedir el resumen o los cierres (diagramas 1 y 2) y en la autenticación de un empleado cuyo turno quedó abierto de un día anterior.

## Casos comunes

El token vencido (se renueva solo y se repite el pedido) está explicado en [`diagrama-secuencia-usuarios.md`](diagrama-secuencia-usuarios.md). Los demás módulos están en [`diagrama-secuencia-ventas.md`](diagrama-secuencia-ventas.md) y [`diagrama-secuencia-productos.md`](diagrama-secuencia-productos.md).
