# Diagramas de secuencia: horarios del personal

Cómo viaja un pedido entre las capas del sistema cuando un dueño **consulta los horarios**, cuando se **da de alta un turno** (alguien empieza a trabajar), cuando se **da de baja** (termina) y cuando el dueño **corrige una hora de salida**. Están hechos a partir del código real (`frontend/src/paginas/Horarios.jsx`, `frontend/src/auth/AuthContext.jsx`, `frontend/src/api.js`, `backend/turnos/api.py`, `backend/turnos/servicios.py`, `backend/turnos/models.py` y `backend/usuarios/views.py`).

## Las capas

| Capa | Qué es | Archivos |
| --- | --- | --- |
| Pantalla | Lo que se ve en el navegador (React) | `Horarios.jsx`, `Login.jsx`, `AuthContext.jsx` |
| Cliente de la API | Agrega el token a cada pedido y lo renueva si venció | `useConsulta.js`, `api.js` |
| Proxy de Vite | Recibe `/api/...` en el puerto 5173 y lo pasa al backend | `vite.config.js` |
| Autenticación y permisos | Verifica quién es y que sea dueño | `AutenticacionConTurno`, `EsAdministrador`, `PasswordAlDia` |
| Vista | Recibe el pedido y coordina | `TurnosView`, `CorregirTurnoView`, `LoginView`, `LogoutView` |
| Servicios | Abren y cierran los turnos | `abrir_turno`, `cerrar_turno`, `cerrar_dias_pendientes` |
| Serializer | Arma cada turno para mostrar | `TurnoSerializer` |
| Modelos (ORM) | Convierten los objetos en consultas SQL | `Turno`, `Usuario`, `RegistroAcceso`, `TokenInvalidado` |
| Base de datos | SQL Server | tablas `turno`, `usuario`, `registro_acceso`, `token_invalidado` |

Un **turno** es el tiempo que un empleado o un encargado tuvo su cuenta abierta: desde que entra con su contraseña hasta que cierra sesión. Eso son sus horas trabajadas. **Nadie carga un turno a mano**: el alta y la baja ocurren solas al entrar y al salir. Los dueños no llevan turno.

Quién puede hacer cada cosa:

| Operación | Quién |
| --- | --- |
| Ver horarios y horas trabajadas | Solo dueños |
| Corregir o confirmar una hora de salida | Solo dueños |
| Abrir y cerrar su propio turno | Empleados y encargados, al entrar y salir del sistema |

## 1. Obtención: ver los horarios

Al abrir la pantalla se hacen tres pedidos a la misma ruta, uno para cada bloque.

```mermaid
sequenceDiagram
    actor Dueno as Dueño
    participant Pantalla as Pantalla Horarios (React)
    participant Cliente as Cliente de la API (api.js)
    participant Proxy as Proxy de Vite
    participant Permisos as Autenticación y permisos
    participant Vista as TurnosView
    participant Servicios as Servicios de turnos
    participant Ser as TurnoSerializer
    participant BD as SQL Server

    Dueno->>Pantalla: Abre Horarios del personal

    par Trabajando ahora
        Pantalla->>Cliente: api GET /api/turnos/ con estado abiertos
    and Para revisar
        Pantalla->>Cliente: api GET /api/turnos/ con estado revisar
    and Horas del período
        Pantalla->>Cliente: api GET /api/turnos/ con desde y hasta
    end

    Note over Cliente,BD: Cada pedido hace este mismo recorrido
    Cliente->>Proxy: GET con el token Bearer
    Proxy->>Permisos: Pasa el pedido al backend
    Note over Permisos: Token válido y es Administrador
    Permisos->>Vista: get
    Vista->>Servicios: cerrar_dias_pendientes
    Note over Servicios: Si algún turno quedó abierto de un día anterior,<br/>lo cierra a las 00:00 y lo marca para revisar
    Note over Vista: Filtra según el pedido,<br/>sin hora de salida, para revisar,<br/>o los que empezaron en esas fechas
    Vista->>BD: SELECT en turno con su usuario y rol
    BD-->>Vista: Turnos
    Vista->>Ser: Convertir a JSON
    Note over Ser: Calcula los minutos trabajados<br/>y agrega cómo se cerró cada uno
    Ser-->>Vista: Turnos con entrada, salida y minutos
    Vista-->>Proxy: 200 con la lista
    Proxy-->>Cliente: 200
    Cliente-->>Pantalla: Turnos
    Pantalla-->>Dueno: Quién trabaja ahora, turnos para revisar<br/>y horas por persona
```

Las horas trabajadas no se guardan: se calculan cada vez como la salida menos la entrada. El total por persona lo suma la pantalla con los turnos que llegaron. Con `?usuario=` se filtra por una persona.

## 2. Alta: el turno se abre al iniciar sesión

```mermaid
sequenceDiagram
    actor Empleado
    participant Pantalla as Pantalla de ingreso (React)
    participant Cliente as Cliente de la API (api.js)
    participant Proxy as Proxy de Vite
    participant Vista as LoginView
    participant Servicios as Servicios de turnos
    participant ORM as Modelos Usuario, Turno y RegistroAcceso
    participant BD as SQL Server

    Empleado->>Pantalla: Escribe su usuario y su contraseña
    Pantalla->>Cliente: api POST /api/auth/login/
    Cliente->>Proxy: POST sin token, todavía no tiene sesión
    Proxy->>Vista: Pasa el pedido al backend
    Vista->>ORM: Buscar al usuario y comparar la contraseña
    ORM->>BD: SELECT en usuario
    BD-->>Vista: Usuario

    alt Contraseña incorrecta, cuenta bloqueada o dada de baja
        Vista->>ORM: Registrar el intento fallido
        ORM->>BD: INSERT en registro_acceso
        Vista-->>Pantalla: 401 con el mensaje
        Pantalla-->>Empleado: No puede entrar
    else Contraseña correcta
        Vista->>ORM: Registrar el ingreso
        ORM->>BD: UPDATE usuario e INSERT en registro_acceso
        Vista->>Servicios: cerrar_dias_pendientes
        Vista->>Servicios: abrir_turno
        alt Es dueño
            Note over Servicios: Los dueños no llevan turno
        else Es empleado o encargado
            Servicios->>ORM: Buscar su turno abierto o crear uno
            ORM->>BD: SELECT en turno, y si no hay, INSERT
            Note over BD: El turno nace con la hora de entrada<br/>y sin hora de salida
        end
        Vista-->>Proxy: 200 con los tokens y el usuario
        Proxy-->>Cliente: 200
        Cliente->>Cliente: Guarda los tokens
        Cliente-->>Pantalla: Sesión iniciada
        Pantalla-->>Empleado: Entra al sistema, ya está contando su horario
    end
```

Si la persona ya tenía un turno abierto (por ejemplo, entró desde otro equipo), sigue con ese: no se abre uno nuevo. Mientras el turno esté abierto, cada pedido que hace anota su última actividad, como mucho una vez por minuto.

## 3. Baja: el turno se cierra al salir

```mermaid
sequenceDiagram
    actor Empleado
    participant Pantalla as Cualquier pantalla (React)
    participant Sesion as Manejo de sesión (AuthContext)
    participant Cliente as Cliente de la API (api.js)
    participant Vista as LogoutView
    participant Servicios as Servicios de turnos
    participant ORM as Modelos Turno, TokenInvalidado y RegistroAcceso
    participant BD as SQL Server

    alt Cierra sesión a mano
        Empleado->>Pantalla: Toca Cerrar sesión
        Pantalla->>Sesion: logout
    else Dejó de usar el sistema
        Note over Sesion: Pasó el tiempo de inactividad
        Sesion->>Sesion: logout con motivo inactividad
    end

    Sesion->>Cliente: api POST /api/auth/logout/
    Cliente->>Vista: POST con el token de renovación y el motivo
    Note over Vista: La persona se identifica con ese token.<br/>Se acepta aunque haya vencido hace menos de un día
    Vista->>ORM: Leer el token y buscar al usuario
    ORM->>BD: SELECT en usuario y en token_invalidado
    BD-->>Vista: Usuario

    alt El token no sirve
        Vista-->>Cliente: 401
    else Esa sesión ya estaba cerrada
        Vista-->>Cliente: 204 sin hacer nada
    else Sesión válida
        Vista->>ORM: Invalidar el token
        ORM->>BD: INSERT en token_invalidado
        Vista->>Servicios: cerrar_turno
        Servicios->>ORM: Poner la hora de salida y cómo se cerró
        ORM->>BD: UPDATE turno
        Vista->>ORM: Registrar la salida
        ORM->>BD: INSERT en registro_acceso
        Vista-->>Cliente: 204
    end
    Cliente->>Cliente: Borra los tokens
    Sesion-->>Pantalla: Vuelve al inicio de sesión
    Pantalla-->>Empleado: Sesión cerrada, su horario dejó de contar
```

El turno guarda **cómo se cerró**, y eso se ve en Horarios:

| Cómo se cerró | Cuándo pasa |
| --- | --- |
| Cerró sesión | La persona tocó «Cerrar sesión» |
| Se cerró por inactividad | Dejó la pantalla sin usar y la sesión se cortó sola |
| Lo cerró el sistema a las 00:00 | No cerró sesión; el planificador cerró el turno a medianoche y lo marcó para revisar |
| Lo cerró un dueño | El dueño lo cerró desde Horarios, o dio de baja al usuario mientras trabajaba |

El cierre de las 00:00 está en [`diagrama-secuencia-resumen-cierre.md`](diagrama-secuencia-resumen-cierre.md).

## 4. Corregir o confirmar una hora de salida

Cuando el sistema cierra un turno a las 00:00, no sabe a qué hora se fue de verdad la persona. El dueño lo revisa.

```mermaid
sequenceDiagram
    actor Dueno as Dueño
    participant Pantalla as Pantalla Horarios (React)
    participant Cliente as Cliente de la API (api.js)
    participant Permisos as Autenticación y permisos
    participant Vista as CorregirTurnoView
    participant ORM as Modelo Turno (ORM)
    participant BD as SQL Server

    Dueno->>Pantalla: Mira un turno marcado para revisar
    alt La hora del sistema está bien
        Dueno->>Pantalla: Toca confirmar
        Pantalla->>Cliente: api POST /api/turnos/ID/corregir/ sin hora
    else Se fue a otra hora
        Dueno->>Pantalla: Escribe la hora real de salida y una nota
        Pantalla->>Cliente: api POST /api/turnos/ID/corregir/ con la hora
    end
    Cliente->>Permisos: POST con el token Bearer
    Note over Permisos: Token válido y es Administrador
    Permisos->>Vista: post
    Vista->>ORM: Buscar el turno
    ORM->>BD: SELECT en turno
    BD-->>Vista: Turno

    alt No se puede
        Note over Vista: El turno no existe, o la salida es anterior a la entrada,<br/>pasa de las 00:00 de ese día o está en el futuro
        Vista-->>Pantalla: 400 o 404 con el mensaje
        Pantalla-->>Dueno: Muestra el mensaje
    else Se puede
        Note over Vista: Guarda la hora que había antes,<br/>pone la nueva y saca la marca de revisar
        Vista->>ORM: Guardar con quién lo corrigió y cuándo
        ORM->>BD: UPDATE turno
        Vista-->>Cliente: 200 con el turno actualizado
        Cliente-->>Pantalla: Turno corregido
        Pantalla->>Cliente: Vuelve a pedir las tres listas
        Pantalla-->>Dueno: El turno sale de Para revisar<br/>y cambian las horas trabajadas
    end
```

La hora que había puesto el sistema no se pierde: queda guardada como hora original, junto con quién la corrigió, cuándo y la nota. La corrección aparece en la Actividad del sistema (grupo «Horarios»). Con esta misma operación el dueño puede cerrar un turno que sigue abierto, indicando la hora de salida.

## Casos comunes

El token vencido está en [`diagrama-secuencia-usuarios.md`](diagrama-secuencia-usuarios.md). Qué pasa cuando alguien quiere seguir usando el sistema con el turno ya cerrado está en [`diagrama-secuencia-ventas.md`](diagrama-secuencia-ventas.md).
