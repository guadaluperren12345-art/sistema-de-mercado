# Diagramas de secuencia: lector e impresora

Cómo funciona por dentro la pantalla **«Lector e impresora»**: probar el lector de códigos de barras, configurar el recibo e imprimir uno de prueba, y cómo usan esos aparatos las demás pantallas. Están hechos a partir del código real (`frontend/src/paginas/Dispositivos.jsx`, `frontend/src/dispositivos.js`, `frontend/src/componentes/Recibo.jsx`, `frontend/src/estilos.css` y `frontend/src/paginas/Venta.jsx`).

## En qué se diferencia de los otros módulos

En los demás módulos casi todo pasa por las tres capas (pantalla, servidor y base de datos). Acá **casi todo ocurre en el navegador**:

- El **lector** no habla con el sistema: se comporta como un teclado que escribe muy rápido y aprieta Enter.
- La **impresora** tampoco: el recibo se manda con la impresión del propio navegador.
- La **configuración** del recibo no se guarda en la base de datos, sino **en cada equipo**, porque cada caja puede tener otra impresora.

Por eso este módulo no tiene alta ni baja en el servidor. Lo único que pide a la API es la lista de productos, para poder decir a qué producto corresponde un código leído.

## Las capas

| Capa | Qué es | Archivos |
| --- | --- | --- |
| Aparatos | Lector de códigos (USB o Bluetooth) e impresora instalada en la computadora | — |
| Navegador | Recibe las teclas del lector, guarda la configuración y maneja la impresión | Chrome u otro |
| Pantalla | Lo que se ve (React) | `Dispositivos.jsx`, `Recibo.jsx` |
| Utilidades de dispositivos | Reconocen al lector, leen y guardan la configuración, mandan a imprimir | `dispositivos.js` |
| Almacenamiento del equipo | Donde queda la configuración del recibo | `localStorage`, clave `mercado.dispositivos` |
| Cliente de la API | Agrega el token al único pedido que se hace | `api.js` |
| Backend y base de datos | Devuelven la lista de productos | `ProductosViewSet`, tabla `producto` |

La pantalla la pueden usar **todos** (dueño, encargado y empleado), porque cada cajero tiene que poder probar los aparatos de su caja.

## 1. Obtención: abrir la pantalla

```mermaid
sequenceDiagram
    actor Cajero
    participant Pantalla as Pantalla Lector e impresora (React)
    participant Util as Utilidades de dispositivos
    participant Equipo as Almacenamiento del equipo
    participant Cliente as Cliente de la API (api.js)
    participant API as Backend (Django)
    participant BD as SQL Server

    Cajero->>Pantalla: Abre Lector e impresora
    Pantalla->>Util: leerConfig
    Util->>Equipo: Lee la clave mercado.dispositivos
    Equipo-->>Util: Configuración guardada, o nada
    Note over Util: Lo que falte se completa con los valores<br/>por defecto, papel de 80 mm
    Util-->>Pantalla: Nombre del negocio, dirección, pie,<br/>ancho del papel e imprimir solo
    Pantalla->>Cliente: api GET /api/productos/
    Cliente->>API: Pedido con el token Bearer
    API->>BD: SELECT en producto
    BD-->>API: Productos con sus códigos
    API-->>Cliente: 200 con la lista
    Cliente-->>Pantalla: Productos
    Pantalla->>Util: useLector, empieza a escuchar el teclado
    Pantalla-->>Cajero: Muestra el campo de prueba del lector,<br/>la configuración y un recibo de ejemplo
```

Este es el único pedido al servidor de todo el módulo. Trae también los productos dados de baja, para poder avisar si el código leído es de uno de ellos.

## 2. Probar el lector de códigos

```mermaid
sequenceDiagram
    actor Cajero
    participant Lector as Lector de códigos
    participant Nav as Navegador
    participant Util as Utilidades de dispositivos
    participant Pantalla as Pantalla Lector e impresora (React)

    Cajero->>Lector: Apunta a un producto y aprieta el gatillo
    Lector->>Nav: Escribe el código tecla por tecla<br/>y al final Enter

    alt El cursor está en el campo de prueba
        Nav->>Pantalla: Las teclas se escriben en el campo
        Pantalla->>Pantalla: Con el Enter toma lo escrito
    else El cursor no está en ningún campo
        Nav->>Util: Avisa cada tecla
        Note over Util: Junta las teclas que llegan con menos<br/>de 100 milisegundos entre una y otra.<br/>Una persona no escribe tan rápido
        Util->>Util: Con el Enter, si juntó 3 o más, es un código
        Util->>Pantalla: Entrega el código leído
    end

    Pantalla->>Util: buscarPorCodigo en la lista de productos
    Note over Util: Busca primero por código de barras<br/>y después por número de producto

    alt Hay un producto con ese código
        Util-->>Pantalla: Producto
        Pantalla-->>Cajero: El lector funciona, leyó ese código<br/>y es tal producto, con su precio
    else Ningún producto tiene ese código
        Util-->>Pantalla: Nada
        Pantalla-->>Cajero: El lector funciona, pero falta cargar<br/>ese código en Productos
    end
```

No hace falta instalar nada: cualquier lector que funcione como teclado sirve. La búsqueda se hace sobre la lista que ya se trajo al abrir la pantalla, sin volver a preguntarle al servidor.

## 3. Configurar el recibo

Es lo más parecido a un «alta» en este módulo, pero se guarda en el equipo, no en la base de datos.

```mermaid
sequenceDiagram
    actor Cajero
    participant Pantalla as Pantalla Lector e impresora (React)
    participant Util as Utilidades de dispositivos
    participant Equipo as Almacenamiento del equipo
    participant Recibo as Recibo de ejemplo

    Cajero->>Pantalla: Cambia el nombre del negocio, la dirección,<br/>el pie, el ancho del papel o imprimir solo
    Pantalla->>Util: guardarConfig con el valor nuevo
    Util->>Equipo: Guarda en la clave mercado.dispositivos

    alt Se pudo guardar
        Equipo-->>Util: Listo
        Util-->>Pantalla: Guardado
        Pantalla-->>Cajero: Guardado en este equipo
    else El navegador no deja guardar
        Equipo-->>Util: Error
        Util-->>Pantalla: No se guardó
        Pantalla-->>Cajero: No se pudo guardar en este navegador
    end

    Pantalla->>Recibo: Vuelve a dibujar el recibo de ejemplo
    Recibo-->>Cajero: Se ve cómo queda con el cambio
```

Se guarda con cada cambio, sin botón de guardar. Como queda en el equipo:

- Hay que configurarlo **una vez en cada caja**.
- Si se borran los datos del navegador, vuelve a los valores por defecto.
- No queda registrado en la Actividad del sistema, porque el servidor no se entera.

## 4. Imprimir un recibo de prueba

```mermaid
sequenceDiagram
    actor Cajero
    participant Pantalla as Pantalla Lector e impresora (React)
    participant Util as Utilidades de dispositivos
    participant Nav as Navegador
    participant Imp as Impresora

    Cajero->>Pantalla: Toca Imprimir recibo de prueba
    Pantalla->>Util: imprimirRecibo con el ancho elegido
    Util->>Nav: Agrega una regla con el tamaño de página,<br/>58 u 80 mm de ancho y sin márgenes
    Util->>Nav: Pide imprimir
    Note over Nav: Los estilos de impresión ocultan todo<br/>menos el recibo que está en pantalla
    Nav-->>Cajero: Abre la ventana de impresión
    Cajero->>Nav: Elige la impresora y confirma
    Nav->>Imp: Manda el recibo
    Imp-->>Cajero: Sale el recibo de prueba en papel
    Util->>Nav: Quita la regla del tamaño de página
```

El recibo de prueba es un ejemplo inventado dentro de la pantalla: no es una venta y no se guarda en ningún lado. Sirve cualquier impresora instalada en Windows. Para que la ventana de impresión no aparezca en cada venta, se puede abrir Chrome con la opción `--kiosk-printing`.

## 5. Cómo lo usa la pantalla Vender

Lo que se prueba y configura acá es lo que después usa la caja.

```mermaid
sequenceDiagram
    actor Cajero
    participant Lector as Lector de códigos
    participant Vender as Pantalla Vender (React)
    participant Util as Utilidades de dispositivos
    participant Equipo as Almacenamiento del equipo
    participant API as Backend (Django)
    participant Imp as Impresora

    Vender->>Util: leerConfig al abrir
    Util->>Equipo: Lee la configuración de esta caja
    Equipo-->>Vender: Ancho del papel, datos del negocio<br/>e imprimir solo

    Cajero->>Lector: Escanea un producto
    Lector->>Util: Código y Enter
    Util->>Vender: Código leído
    Vender->>Vender: Lo busca y lo suma a la venta

    Cajero->>Vender: Toca Cobrar
    Vender->>API: POST /api/ventas/
    API-->>Vender: Recibo guardado

    alt Imprimir solo está activado
        Vender->>Util: imprimirRecibo apenas llega el recibo
    else Está desactivado
        Cajero->>Vender: Toca Imprimir recibo si lo quiere en papel
        Vender->>Util: imprimirRecibo
    end
    Util->>Imp: Impresión del navegador
```

El lector también funciona en Vender cuando el recibo de la venta anterior todavía está en pantalla: al escanear, empieza una venta nueva. El recibo queda guardado en el servidor se imprima o no. El detalle de cobrar está en [`diagrama-secuencia-ventas.md`](diagrama-secuencia-ventas.md) y el de reimprimir, en [`diagrama-secuencia-recibos.md`](diagrama-secuencia-recibos.md).

## Pendiente

Todo esto se probó simulando el lector desde el teclado y sin mandar nada a una impresora de verdad. **Falta probarlo con un lector y una impresora reales.**
