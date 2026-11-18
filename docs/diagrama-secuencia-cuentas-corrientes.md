# Diagramas de secuencia: cuentas corrientes

Cómo viaja un pedido entre las capas del sistema cuando alguien **consulta** los clientes de cuenta corriente, **da de alta** o **da de baja** un cliente, **cobra un pago** de la deuda o **cambia el límite de fiado**. Están hechos a partir del código real (`frontend/src/paginas/Clientes.jsx`, `frontend/src/api.js`, `backend/clientes/api.py`, `backend/clientes/servicios.py`, `backend/clientes/models.py` y `backend/usuarios/permisos.py`).

## Las capas

| Capa | Qué es | Archivos |
| --- | --- | --- |
| Pantalla | Lo que se ve en el navegador (React) | `Clientes.jsx` |
| Cliente de la API | Agrega el token a cada pedido y lo renueva si venció | `api.js` |
| Proxy de Vite | Recibe `/api/...` en el puerto 5173 y lo pasa al backend | `vite.config.js` |
| Autenticación y permisos | Verifica quién es, su turno y qué puede hacer | `AutenticacionConTurno`, `GestionaClientes`, `EsAdministrador`, `PasswordAlDia` |
| Vista | Recibe el pedido y coordina | `ClientesViewSet`, `ConfiguracionView` |
| Serializer | Valida los datos y arma la respuesta | `ClienteSerializer`, `PagoSerializer`, `MovimientoSerializer` |
| Reglas de cuenta | Cambian la deuda dejando siempre un movimiento | `bloquear`, `registrar`, `limite_de` |
| Modelos (ORM) | Convierten los objetos en consultas SQL | `Cliente`, `MovimientoCuenta`, `CambioCliente`, `ConfiguracionCuentas` |
| Base de datos | SQL Server | tablas `cliente`, `movimiento_cuenta`, `cambio_cliente`, `configuracion_cuentas` |

En el código, «el cliente de la API» es el archivo que hace los pedidos; no tiene nada que ver con los clientes del mercado.

Quién puede hacer cada cosa:

| Operación | Quién |
| --- | --- |
| Ver los clientes y su cuenta | Todos |
| Cobrar un pago | Todos (cualquier cajero) |
| Dar de alta, corregir y dar de baja clientes | Dueños, y los encargados que un dueño autorizó |
| Fijar el límite general y el de cada cliente | Solo dueños |
| Ajustar una cuenta a mano | Solo dueños |

La deuda de un cliente funciona como el stock: **nadie la escribe a mano**. Solo cambia con un movimiento (compra fiada, pago, anulación o ajuste), y cada movimiento guarda quién lo hizo, cuándo y cómo quedó la deuda.

## 1. Obtención: ver los clientes y sus deudas

Al abrir la pantalla se hacen dos pedidos: la lista de clientes y el límite general.

```mermaid
sequenceDiagram
    actor Usuario
    participant Pantalla as Pantalla Cuentas corrientes (React)
    participant Cliente as Cliente de la API (api.js)
    participant Proxy as Proxy de Vite
    participant Auth as Autenticación y turno
    participant Vista as ClientesViewSet
    participant Ser as ClienteSerializer
    participant ORM as Modelos Cliente y ConfiguracionCuentas
    participant BD as SQL Server

    Usuario->>Pantalla: Abre Cuentas corrientes

    par Lista de clientes
        Pantalla->>Cliente: api GET /api/clientes/
    and Límite general
        Pantalla->>Cliente: api GET /api/cuentas/configuracion/
    end

    Cliente->>Proxy: GET /api/clientes/ con el token Bearer
    Proxy->>Auth: Pasa el pedido al backend
    Auth->>BD: Busca al usuario y su turno abierto
    BD-->>Auth: Usuario, rol y turno
    Note over Auth: Alcanza con tener sesión
    Auth->>Vista: list
    Vista->>ORM: Leer el límite general
    ORM->>BD: SELECT en configuracion_cuentas
    BD-->>Vista: Límite general, o sin límite
    Vista->>ORM: Clientes ordenados por nombre
    ORM->>BD: SELECT en cliente
    BD-->>ORM: Filas
    ORM-->>Vista: Lista de clientes
    Vista->>Ser: Convertir a JSON
    Note over Ser: Para cada cliente calcula el límite que le toca,<br/>el propio o el general, y cuánto le queda para fiar
    Ser-->>Vista: Clientes con deuda, límite y disponible
    Vista-->>Proxy: 200 con la lista
    Proxy-->>Cliente: 200
    Cliente-->>Pantalla: Clientes y límite general
    Pantalla-->>Usuario: Muestra cuánto debe cada uno<br/>y el total que se debe
```

Las pestañas (Activos, Dados de baja, Solo los que deben) y el buscador no vuelven a llamar al servidor. El total «Deben en total» lo suma la pantalla. Lo que cada persona puede hacer con la lista depende de `gestiona_clientes`, que llega con los datos del usuario al iniciar sesión.

Para **ver la cuenta** de un cliente se hace otro pedido, `GET /api/clientes/ID/movimientos/`, que devuelve sus últimos 200 movimientos con el mismo recorrido.

## 2. Alta: cargar un cliente

```mermaid
sequenceDiagram
    actor Encargado as Dueño o encargado autorizado
    participant Pantalla as Pantalla Cuentas corrientes (React)
    participant Cliente as Cliente de la API (api.js)
    participant Proxy as Proxy de Vite
    participant Permisos as Autenticación y permisos
    participant Vista as ClientesViewSet
    participant Ser as ClienteSerializer
    participant ORM as Modelos Cliente y CambioCliente
    participant BD as SQL Server

    Encargado->>Pantalla: Toca Nuevo cliente y completa<br/>nombre, DNI, teléfono, dirección y nota
    Pantalla->>Cliente: api POST /api/clientes/
    Cliente->>Proxy: POST /api/clientes/ con el token Bearer
    Proxy->>Permisos: Pasa el pedido al backend
    Permisos->>BD: Busca al usuario del token
    BD-->>Permisos: Usuario, rol y si puede cargar clientes

    alt No puede cargar clientes
        Note over Permisos: Es empleado, o es encargado<br/>y ningún dueño lo autorizó
        Permisos-->>Pantalla: 403
        Pantalla-->>Encargado: Muestra el mensaje
    else Es dueño o encargado autorizado
        Permisos->>Vista: create
        Vista->>Ser: Validar los datos
        Note over Ser: Ordena el nombre y le saca los puntos al DNI
        Ser->>BD: Consulta si ya hay otro con ese nombre o ese DNI
        BD-->>Ser: No hay
        Note over Ser: Si viene un límite propio,<br/>controla que quien lo pone sea dueño

        alt Algún dato está mal
            Ser-->>Vista: Errores por campo
            Vista-->>Pantalla: 400 con los mensajes
            Pantalla-->>Encargado: Marca el campo con el error
        else Todo bien
            Note over Vista,BD: Una sola transacción
            Ser->>ORM: Crear el cliente con deuda 0
            ORM->>BD: INSERT en cliente
            Vista->>ORM: Registrar el alta
            ORM->>BD: INSERT en cambio_cliente, acción ALTA
            Vista-->>Proxy: 201 con el cliente creado
            Proxy-->>Cliente: 201
            Cliente-->>Pantalla: Cliente creado
            Pantalla-->>Encargado: Aparece en la lista, listo para fiarle
        end
    end
```

El permiso del encargado lo da un dueño desde la pantalla Usuarios, con la casilla «Puede cargar clientes de cuenta corriente» (`POST /api/usuarios/ID/permiso-clientes/`). Aunque esté autorizado, un encargado no puede ponerle límite a un cliente: eso es solo de los dueños. Corregir los datos de un cliente (`PATCH /api/clientes/ID/`) hace el mismo recorrido y registra la acción `EDICION`.

## 3. Baja: dar de baja un cliente

```mermaid
sequenceDiagram
    actor Encargado as Dueño o encargado autorizado
    participant Pantalla as Pantalla Cuentas corrientes (React)
    participant Cliente as Cliente de la API (api.js)
    participant Proxy as Proxy de Vite
    participant Permisos as Autenticación y permisos
    participant Vista as ClientesViewSet
    participant ORM as Modelos Cliente y CambioCliente
    participant BD as SQL Server

    Encargado->>Pantalla: Toca Dar de baja
    Pantalla-->>Encargado: Pide confirmar y un motivo opcional.<br/>Avisa si todavía debe plata
    Encargado->>Pantalla: Confirma
    Pantalla->>Cliente: api POST /api/clientes/ID/desactivar/
    Cliente->>Proxy: POST con el token Bearer y el motivo
    Proxy->>Permisos: Pasa el pedido al backend
    Note over Permisos: Tiene que ser dueño o encargado autorizado
    Permisos->>Vista: desactivar
    Vista->>ORM: Buscar al cliente
    ORM->>BD: SELECT en cliente
    BD-->>Vista: Cliente

    alt Ya estaba dado de baja
        Vista-->>Pantalla: 400 con el mensaje
        Pantalla-->>Encargado: Muestra el mensaje
    else Se puede
        Note over Vista,BD: Una sola transacción
        Vista->>ORM: Marcar activo en falso
        ORM->>BD: UPDATE cliente
        Vista->>ORM: Registrar la baja con el motivo
        ORM->>BD: INSERT en cambio_cliente, acción BAJA
        Vista-->>Proxy: 200 con el cliente actualizado
        Proxy-->>Cliente: 200
        Cliente-->>Pantalla: Cliente dado de baja
        Pantalla-->>Encargado: Pasa a la pestaña Dados de baja
    end
```

El cliente **no se borra** y su deuda tampoco: queda con `activo` en falso. No se le puede fiar más, pero lo que debe se puede seguir cobrando. Se reactiva con `POST /api/clientes/ID/reactivar/`.

## 4. Cobrar un pago de la deuda

Lo puede hacer cualquier cajero.

```mermaid
sequenceDiagram
    actor Cajero
    participant Pantalla as Pantalla Cuentas corrientes (React)
    participant Cliente as Cliente de la API (api.js)
    participant Auth as Autenticación y turno
    participant Vista as ClientesViewSet
    participant Ser as PagoSerializer
    participant Reglas as Reglas de cuenta
    participant BD as SQL Server

    Cajero->>Pantalla: Toca Cobrar pago
    Pantalla-->>Cajero: Propone cobrar todo lo que debe
    Cajero->>Pantalla: Escribe el importe y cómo paga
    Pantalla->>Cliente: api POST /api/clientes/ID/pago/
    Cliente->>Auth: POST con el token Bearer
    Note over Auth: Alcanza con tener sesión
    Auth->>Vista: pago
    Vista->>Ser: Validar importe y medio de pago
    Note over Ser: El importe tiene que ser mayor a 0.<br/>La deuda no se paga con cuenta corriente

    Note over Vista,BD: Una sola transacción
    Vista->>Reglas: bloquear al cliente
    Reglas->>BD: SELECT con bloqueo en cliente
    BD-->>Vista: Cliente y su deuda

    alt No se puede cobrar
        Note over Vista: No debe nada, o el importe<br/>es más de lo que debe
        Vista-->>Pantalla: 400 con el mensaje
        Pantalla-->>Cajero: Muestra el mensaje
    else Se puede
        Vista->>Reglas: registrar el pago
        Reglas->>BD: UPDATE cliente, baja la deuda
        Reglas->>BD: INSERT en movimiento_cuenta, tipo PAGO,<br/>con el medio de pago y la deuda que queda
        Vista-->>Cliente: 201 con el cliente y el comprobante
        Cliente-->>Pantalla: Pago cobrado
        Pantalla-->>Cajero: Muestra el comprobante,<br/>lo que pagó y lo que sigue debiendo
        opt Imprimir
            Pantalla->>Pantalla: Impresión del navegador
        end
    end
```

El bloqueo del cliente evita que dos cajas cobrándole a la vez pisen su deuda. El pago se guarda en negativo (baja la deuda) y su número sirve como número de comprobante. La plata cobrada entra en la cuenta final del día; si fue en efectivo, también suma al efectivo que debería haber en la caja.

Cómo se **anota una compra fiada** (lo que hace subir la deuda) está en [`diagrama-secuencia-ventas.md`](diagrama-secuencia-ventas.md).

## 5. Cambiar el límite general de fiado

Solo los dueños.

```mermaid
sequenceDiagram
    actor Dueno as Dueño
    participant Pantalla as Pantalla Cuentas corrientes (React)
    participant Cliente as Cliente de la API (api.js)
    participant Permisos as Autenticación y permisos
    participant Vista as ConfiguracionView
    participant ORM as Modelos ConfiguracionCuentas y CambioCliente
    participant BD as SQL Server

    Dueno->>Pantalla: Toca Cambiar en Límite general de fiado
    Dueno->>Pantalla: Escribe el límite, o lo deja vacío
    Pantalla->>Cliente: api POST /api/cuentas/configuracion/
    Cliente->>Permisos: POST con el token Bearer
    Note over Permisos: Tiene que ser Administrador.<br/>A los demás les responde 403
    Permisos->>Vista: post

    alt El valor no es un número válido
        Vista-->>Pantalla: 400 con el mensaje
        Pantalla-->>Dueno: Muestra el mensaje
    else Valor correcto
        Note over Vista,BD: Una sola transacción
        Vista->>ORM: Leer la configuración
        ORM->>BD: SELECT con bloqueo en configuracion_cuentas
        opt El límite cambió
            Vista->>ORM: Registrar el cambio
            ORM->>BD: INSERT en cambio_cliente, acción LIMITE_GENERAL
            Vista->>ORM: Guardar el límite nuevo
            ORM->>BD: UPDATE configuracion_cuentas
        end
        Vista-->>Cliente: 200 con el límite general
        Cliente-->>Pantalla: Límite guardado
        Pantalla->>Cliente: Vuelve a pedir los clientes
        Pantalla-->>Dueno: Cambia cuánto le queda a cada cliente
    end
```

Cómo se decide el límite de cada cliente: si tiene uno **propio**, vale ese; si no, vale el **general**; si tampoco hay general, no tiene tope. El límite propio se cambia desde «Editar» en el cliente (`PATCH /api/clientes/ID/`) y registra la acción `LIMITE`. Vacío significa «sin límite general»; el límite propio vacío significa «usa el general».

El **ajuste a mano** de una cuenta (`POST /api/clientes/ID/ajuste/`, solo dueños) sigue el mismo recorrido que el pago, con un importe con signo y un motivo obligatorio. Sirve para cargar lo que el cliente ya debía en el cuaderno o corregir un error.

## Casos comunes

El token vencido está en [`diagrama-secuencia-usuarios.md`](diagrama-secuencia-usuarios.md) y el turno cerrado en [`diagrama-secuencia-ventas.md`](diagrama-secuencia-ventas.md). Cómo entran lo fiado y los pagos en la cuenta final y en el cierre de las 00:45 está en [`diagrama-secuencia-resumen-cierre.md`](diagrama-secuencia-resumen-cierre.md).
