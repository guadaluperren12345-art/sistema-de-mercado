# Diagramas de secuencia: usuarios

Cómo viaja un pedido entre las capas del sistema cuando un dueño **consulta**, **da de alta** o **da de baja** a un usuario. Están hechos a partir del código real (`frontend/src/paginas/Usuarios.jsx`, `NuevoUsuario.jsx`, `frontend/src/api.js`, `backend/usuarios/gestion.py`, `backend/usuarios/permisos.py` y `backend/turnos/autenticacion.py`).

## Las capas

| Capa | Qué es | Archivos |
| --- | --- | --- |
| Pantalla | Lo que ve el dueño en el navegador (React) | `Usuarios.jsx`, `NuevoUsuario.jsx` |
| Cliente de la API | Agrega el token a cada pedido y lo renueva si venció | `api.js` |
| Proxy de Vite | Recibe `/api/...` en el puerto 5173 y lo pasa al backend | `vite.config.js` |
| Autenticación y permisos | Verifica quién es y si es dueño | `AutenticacionConTurno`, `EsAdministrador`, `PasswordAlDia` |
| Vista | Recibe el pedido y coordina | `UsuariosViewSet` |
| Serializer | Valida los datos y arma la respuesta | `UsuarioAltaSerializer`, `UsuarioListaSerializer` |
| Modelos (ORM) | Convierten los objetos en consultas SQL | `Usuario`, `CambioUsuario`, `Turno` |
| Base de datos | SQL Server | tablas `usuario`, `cambio_usuario`, `turno` |

Las tres operaciones son **solo para dueños** (rol Administrador). Si el que pregunta no lo es, la capa de permisos corta el pedido con un error 403 antes de llegar a la vista.

## 1. Obtención: ver la lista de usuarios

```mermaid
sequenceDiagram
    actor Dueno as Dueño
    participant Pantalla as Pantalla Usuarios (React)
    participant Cliente as Cliente de la API (api.js)
    participant Proxy as Proxy de Vite
    participant Permisos as Autenticación y permisos
    participant Vista as UsuariosViewSet
    participant Ser as UsuarioListaSerializer
    participant ORM as Modelo Usuario (ORM)
    participant BD as SQL Server

    Dueno->>Pantalla: Abre Usuarios
    Pantalla->>Cliente: api GET /api/usuarios/
    Cliente->>Proxy: GET /api/usuarios/ con el token Bearer
    Proxy->>Permisos: Pasa el pedido al backend
    Permisos->>BD: Busca al usuario del token
    BD-->>Permisos: Usuario y rol
    Note over Permisos: Token válido, es Administrador<br/>y tiene la contraseña al día
    Permisos->>Vista: list
    Vista->>ORM: Usuarios con su rol y quién los creó,<br/>ordenados por apellido
    ORM->>BD: SELECT en usuario y rol
    BD-->>ORM: Filas
    ORM-->>Vista: Lista de usuarios
    Vista->>Ser: Convertir a JSON
    Ser-->>Vista: nombre, rol, activo, bloqueado, último acceso
    Vista-->>Proxy: 200 con la lista
    Proxy-->>Cliente: 200 con la lista
    Cliente-->>Pantalla: Lista de usuarios
    Pantalla-->>Dueno: Muestra Activos y Dados de baja
```

Con `?activo=1` o `?activo=0` la vista filtra antes de consultar. El buscador de la pantalla no vuelve a llamar al servidor: filtra la lista que ya tiene.

## 2. Alta: crear un usuario

```mermaid
sequenceDiagram
    actor Dueno as Dueño
    participant Pantalla as Pantalla Nuevo usuario (React)
    participant Cliente as Cliente de la API (api.js)
    participant Proxy as Proxy de Vite
    participant Permisos as Autenticación y permisos
    participant Vista as UsuariosViewSet
    participant Ser as UsuarioAltaSerializer
    participant ORM as Modelos Usuario y CambioUsuario
    participant BD as SQL Server

    Dueno->>Pantalla: Completa nombre, DNI, rol<br/>y contraseña inicial
    Pantalla->>Pantalla: Revisa que no falte nada
    Pantalla->>Cliente: api POST /api/usuarios/
    Cliente->>Proxy: POST /api/usuarios/ con el token Bearer
    Proxy->>Permisos: Pasa el pedido al backend
    Note over Permisos: Token válido y es Administrador
    Permisos->>Vista: create
    Vista->>Ser: Validar los datos
    Note over Ser: Pasa el usuario a minúsculas<br/>y le saca los puntos al DNI
    Ser->>BD: Consulta si ya existe ese usuario o ese DNI
    BD-->>Ser: No existen
    Note over Ser: Controla formato del usuario y del DNI,<br/>el rol y la regla de contraseñas

    alt Algún dato está mal
        Ser-->>Vista: Errores por campo
        Vista-->>Pantalla: 400 con los mensajes
        Pantalla-->>Dueno: Marca el campo con el error
    else Todo bien
        Note over Vista,BD: Una sola transacción
        Ser->>ORM: Crear el usuario, con cambio<br/>de contraseña obligatorio
        ORM->>BD: INSERT en usuario con la contraseña cifrada
        Vista->>ORM: Registrar el alta
        ORM->>BD: INSERT en cambio_usuario, acción ALTA
        Vista-->>Proxy: 201 con el usuario creado
        Proxy-->>Cliente: 201
        Cliente-->>Pantalla: Usuario creado
        Pantalla-->>Dueno: Muestra usuario y contraseña<br/>para pasárselos a la persona
    end
```

La contraseña nunca se guarda tal cual: Django guarda solo su versión cifrada. La persona está obligada a cambiarla en su primer ingreso.

## 3. Baja: dar de baja a un usuario

```mermaid
sequenceDiagram
    actor Dueno as Dueño
    participant Pantalla as Pantalla Usuarios (React)
    participant Cliente as Cliente de la API (api.js)
    participant Proxy as Proxy de Vite
    participant Permisos as Autenticación y permisos
    participant Vista as UsuariosViewSet
    participant Turnos as Servicio de turnos
    participant ORM as Modelos Usuario, Turno y CambioUsuario
    participant BD as SQL Server

    Dueno->>Pantalla: Toca Dar de baja
    Pantalla-->>Dueno: Pide confirmar y un motivo opcional
    Dueno->>Pantalla: Confirma
    Pantalla->>Cliente: api POST /api/usuarios/ID/desactivar/
    Cliente->>Proxy: POST con el token Bearer y el motivo
    Proxy->>Permisos: Pasa el pedido al backend
    Note over Permisos: Token válido y es Administrador
    Permisos->>Vista: desactivar
    Vista->>ORM: Buscar al usuario
    ORM->>BD: SELECT en usuario
    BD-->>Vista: Usuario

    alt No se puede dar de baja
        Note over Vista: Es su propia cuenta, ya estaba de baja<br/>o es el último dueño activo
        Vista-->>Pantalla: 400 con el motivo
        Pantalla-->>Dueno: Muestra el mensaje
    else Se puede
        Note over Vista,BD: Una sola transacción
        Vista->>ORM: Marcar activo en falso
        ORM->>BD: UPDATE usuario
        Vista->>Turnos: Cerrar su turno si estaba trabajando
        Turnos->>BD: UPDATE turno con la hora de salida
        Vista->>ORM: Registrar la baja con el motivo
        ORM->>BD: INSERT en cambio_usuario, acción BAJA
        Vista-->>Proxy: 200 con el usuario actualizado
        Proxy-->>Cliente: 200
        Cliente-->>Pantalla: Usuario dado de baja
        Pantalla-->>Dueno: Pasa a la pestaña Dados de baja
    end
```

El usuario **no se borra**: queda con `activo` en falso, deja de poder ingresar y su sesión abierta se corta porque su turno se cerró. Se puede reactivar con `POST /api/usuarios/ID/reactivar/`, que hace el camino inverso y registra la acción `REACTIVACION`.

## Qué pasa si el token venció

En cualquiera de los tres casos, si el token de acceso ya venció (dura 15 minutos), el cliente lo renueva solo y repite el pedido una vez:

```mermaid
sequenceDiagram
    participant Pantalla as Pantalla (React)
    participant Cliente as Cliente de la API (api.js)
    participant API as Backend (Django)

    Pantalla->>Cliente: api GET /api/usuarios/
    Cliente->>API: Pedido con el token vencido
    API-->>Cliente: 401
    Cliente->>API: POST /api/auth/refresh/
    API-->>Cliente: Tokens nuevos
    Cliente->>API: Repite el pedido con el token nuevo
    API-->>Cliente: 200 con los datos
    Cliente-->>Pantalla: Datos
```

Si la renovación también falla, el cliente avisa que la sesión terminó y la pantalla vuelve al inicio de sesión.
