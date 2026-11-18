# Diagramas de secuencia: gastos

Cómo viaja un pedido entre las capas del sistema cuando alguien **consulta** la lista de gastos, **da de alta** (anota) un gasto o **da de baja** (anula) uno, y cómo esos gastos terminan restando en la cuenta final del día. Están hechos a partir del código real (`frontend/src/paginas/Gastos.jsx`, `frontend/src/useConsulta.js`, `frontend/src/api.js`, `backend/gastos/api.py`, `backend/gastos/models.py` y `backend/turnos/servicios.py`).

## Las capas

| Capa | Qué es | Archivos |
| --- | --- | --- |
| Pantalla | Lo que se ve en el navegador (React) | `Gastos.jsx` |
| Cliente de la API | Agrega el token a cada pedido y lo renueva si venció | `useConsulta.js`, `api.js` |
| Proxy de Vite | Recibe `/api/...` en el puerto 5173 y lo pasa al backend | `vite.config.js` |
| Autenticación y turno | Verifica quién es y que tenga su turno abierto | `AutenticacionConTurno`, `PasswordAlDia` |
| Vista | Recibe el pedido y coordina | `GastosViewSet` |
| Serializer | Valida los datos y arma la respuesta | `GastoSerializer` |
| Modelos (ORM) | Convierten los objetos en consultas SQL | `Gasto` |
| Base de datos | SQL Server | tabla `gasto` |

Los gastos son una **lista simple**, como una hoja de anotaciones: cada renglón es un monto y, al lado, para qué fue.

Quién puede hacer cada cosa:

| Operación | Quién |
| --- | --- |
| Anotar un gasto | Todos (dueño, encargado y empleado) |
| Ver la lista de hoy | Todos |
| Ver la lista de otro día | Dueños y encargados |
| Anular un gasto | Quien lo anotó, ese mismo día; encargados y dueños, cualquiera |

## 1. Obtención: ver la lista de gastos

```mermaid
sequenceDiagram
    actor Usuario
    participant Pantalla as Pantalla Gastos (React)
    participant Cliente as Cliente de la API (api.js)
    participant Proxy as Proxy de Vite
    participant Auth as Autenticación y turno
    participant Vista as GastosViewSet
    participant Ser as GastoSerializer
    participant ORM as Modelo Gasto (ORM)
    participant BD as SQL Server

    Usuario->>Pantalla: Abre Gastos o elige otro día
    Pantalla->>Cliente: api GET /api/gastos/ con la fecha
    Cliente->>Proxy: GET con el token Bearer
    Proxy->>Auth: Pasa el pedido al backend
    Auth->>BD: Busca al usuario y su turno abierto
    BD-->>Auth: Usuario, rol y turno
    Note over Auth: Alcanza con tener sesión
    Auth->>Vista: list
    Vista->>Vista: Lee la fecha pedida. Sin fecha, es hoy

    alt No puede ver ese día
        Note over Vista: La fecha está mal escrita,<br/>o es empleado y pide un día que no es hoy
        Vista-->>Pantalla: 400 o 403 con el mensaje
        Pantalla-->>Usuario: Muestra el mensaje
    else Puede verlo
        Vista->>ORM: Gastos de ese día con quién los anotó
        ORM->>BD: SELECT en gasto, hasta 500
        BD-->>ORM: Filas
        ORM-->>Vista: Gastos del día
        Note over Vista: Suma el total y cuenta los gastos.<br/>Los anulados no suman
        Vista->>Ser: Convertir a JSON
        Note over Ser: Agrega a cada gasto si esta persona<br/>lo puede anular
        Ser-->>Vista: Gastos
        Vista-->>Proxy: 200 con fecha, cantidad, total y gastos
        Proxy-->>Cliente: 200
        Cliente-->>Pantalla: Lista del día
        Pantalla-->>Usuario: Lista con el total en negativo al pie
    end
```

Los gastos anulados siguen viniendo en la lista (se muestran tachados), pero no entran en el total. El selector de otro día solo le aparece a dueños y encargados.

## 2. Alta: anotar un gasto

```mermaid
sequenceDiagram
    actor Usuario
    participant Pantalla as Pantalla Gastos (React)
    participant Cliente as Cliente de la API (api.js)
    participant Proxy as Proxy de Vite
    participant Auth as Autenticación y turno
    participant Vista as GastosViewSet
    participant Ser as GastoSerializer
    participant ORM as Modelo Gasto (ORM)
    participant BD as SQL Server

    Usuario->>Pantalla: Escribe el monto y para qué fue
    Pantalla->>Pantalla: Revisa que el monto sea un número<br/>mayor a 0 y que haya un propósito
    Pantalla->>Cliente: api POST /api/gastos/
    Cliente->>Proxy: POST /api/gastos/ con el token Bearer
    Proxy->>Auth: Pasa el pedido al backend
    Auth->>BD: Busca al usuario y su turno abierto
    BD-->>Auth: Usuario y turno
    Note over Auth: Alcanza con tener sesión.<br/>Cualquiera puede anotar
    Auth->>Vista: create
    Vista->>Ser: Validar monto y propósito
    Note over Ser: El monto tiene que ser mayor a 0.<br/>Ordena el texto del propósito

    alt Algún dato está mal
        Ser-->>Vista: Errores por campo
        Vista-->>Pantalla: 400 con los mensajes
        Pantalla-->>Usuario: Marca el campo con el error
    else Todo bien
        Ser->>ORM: Crear el gasto a nombre del usuario<br/>y en su turno
        ORM->>BD: INSERT en gasto, con fecha y hora del sistema
        Vista-->>Proxy: 201 con el gasto anotado
        Proxy-->>Cliente: 201
        Cliente-->>Pantalla: Gasto anotado
        Pantalla->>Cliente: Vuelve a pedir la lista de hoy
        Pantalla-->>Usuario: Aparece arriba en la lista y cambia el total
    end
```

El monto se guarda en positivo; es en las cuentas donde se resta. La fecha y la hora las pone el sistema. Un gasto anotado por un dueño queda sin turno, porque los dueños no llevan turno. Después de anotar, el cursor vuelve al monto para cargar el siguiente.

## 3. Baja: anular un gasto

```mermaid
sequenceDiagram
    actor Usuario
    participant Pantalla as Pantalla Gastos (React)
    participant Cliente as Cliente de la API (api.js)
    participant Proxy as Proxy de Vite
    participant Auth as Autenticación y turno
    participant Vista as GastosViewSet
    participant ORM as Modelo Gasto (ORM)
    participant BD as SQL Server

    Usuario->>Pantalla: Toca Anular en un gasto
    Note over Pantalla: El botón solo aparece en los gastos<br/>que esta persona puede anular
    Pantalla-->>Usuario: Pide confirmar y un motivo opcional
    Usuario->>Pantalla: Confirma
    Pantalla->>Cliente: api POST /api/gastos/ID/anular/
    Cliente->>Proxy: POST con el token Bearer y el motivo
    Proxy->>Auth: Pasa el pedido al backend
    Note over Auth: Alcanza con tener sesión.<br/>El permiso se revisa más adelante, gasto por gasto
    Auth->>Vista: anular

    Note over Vista,BD: Una sola transacción
    Vista->>ORM: Buscar el gasto
    ORM->>BD: SELECT con bloqueo en gasto
    BD-->>Vista: Gasto

    alt No se puede anular
        Note over Vista: No existe, ya estaba anulado, o es empleado<br/>y el gasto no es suyo o no es de hoy
        Vista-->>Pantalla: 404, 400 o 403 con el mensaje
        Pantalla-->>Usuario: Muestra el mensaje
    else Se puede
        Vista->>ORM: Marcar anulado con quién, cuándo y por qué
        ORM->>BD: UPDATE gasto
        Vista-->>Proxy: 200 con el gasto anulado
        Proxy-->>Cliente: 200
        Cliente-->>Pantalla: Gasto anulado
        Pantalla->>Cliente: Vuelve a pedir la lista
        Pantalla-->>Usuario: Queda tachado y deja de restar en el total
    end
```

El gasto **no se borra ni se edita**: queda en la lista tachado, con quién lo anuló y el motivo. Si se anotó mal, se anula y se anota de nuevo. Un gasto anulado no se puede volver a activar.

A diferencia de otros módulos, acá el permiso no lo decide solo el rol: depende de **quién anotó el gasto y de qué día es**, así que lo revisa la vista con el gasto en la mano.

## 4. Cómo llegan los gastos al cierre del día

Los gastos no restan de nada en el momento de anotarlos. Se suman cuando un dueño mira el resumen y cuando el sistema hace el cierre de las 00:45.

```mermaid
sequenceDiagram
    actor Dueno as Dueño
    participant Resumen as Pantalla Resumen (React)
    participant Plan as Planificador (contenedor tareas)
    participant Servicios as Servicios de turnos
    participant BD as SQL Server

    alt El dueño mira el resumen
        Dueno->>Resumen: Abre Resumen y cierre del día
        Resumen->>Servicios: GET /api/resumen/
    else Pasan las 00:45
        Plan->>Servicios: cerrar_dias_pendientes
    end

    Servicios->>BD: SELECT en gasto del período
    BD-->>Servicios: Gastos
    Note over Servicios: resumen_de_gastos<br/>suma los que no están anulados
    Servicios->>BD: Lee ventas, pagos de cuentas corrientes<br/>y pagos a comerciantes
    BD-->>Servicios: Plata que entró y que salió
    Note over Servicios: cuenta_final<br/>plata que entró menos gastos<br/>menos pagos a comerciantes

    alt Era el resumen
        Servicios-->>Resumen: Cuenta final con los gastos en negativo
        Resumen-->>Dueno: Muestra la cuenta final y la lista de gastos
    else Era el cierre de las 00:45
        Servicios->>BD: INSERT en cierre_diario con cantidad<br/>y total de gastos del día
    end
```

Los gastos se restan de dos números: de la **cuenta final** (lo que entró menos lo que salió) y del **efectivo que debería haber en la caja**, porque se asume que se pagan con la plata de la caja. El detalle del resumen y del cierre está en [`diagrama-secuencia-resumen-cierre.md`](diagrama-secuencia-resumen-cierre.md).

Los gastos no tienen sección: en **Resultados por sección** se restan una sola vez, en el resultado del mercado entero.

## Casos comunes

El token vencido está en [`diagrama-secuencia-usuarios.md`](diagrama-secuencia-usuarios.md) y el turno cerrado en [`diagrama-secuencia-ventas.md`](diagrama-secuencia-ventas.md).
