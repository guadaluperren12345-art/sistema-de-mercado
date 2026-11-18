import { useState } from 'react'
import { api } from '../api'
import { EVENTO_AVISOS } from '../avisos'
import Encabezado from '../componentes/Encabezado'
import { fechaHora, HORA_CIERRE } from '../formato'
import { useConsulta } from '../useConsulta'

// Avisos a los dueños (RF-123 a RF-131). Solo dueños.
// Cada noche a las 00:45 el sistema hace la caja del día y se la manda a cada dueño por tres caminos,
// por si alguno falla: acá adentro, por Telegram y por correo. En esta pantalla se leen los avisos
// y se configura por dónde llegan.

const puedeNotificar = () => typeof window !== 'undefined' && 'Notification' in window && window.isSecureContext

function Canal({ ok, children }) {
  return <span className={`etiqueta sin-margen ${ok ? 'etiqueta-verde' : 'etiqueta-roja'}`}>{children}</span>
}

function Aviso({ aviso, onLeer }) {
  const [abierto, setAbierto] = useState(!aviso.leida)
  return (
    <li className={`tarjeta aviso ${aviso.leida ? '' : 'aviso-nuevo'}`}>
      <div className="titulo-con-accion">
        <div className="datos-usuario">
          <strong>{aviso.titulo} {!aviso.leida && <span className="etiqueta etiqueta-venta">Nuevo</span>}</strong>
          <small className="texto-suave">
            {fechaHora(aviso.creada_en)}
            {aviso.envios.map((e) => (
              <span key={e.canal} title={e.error || undefined}> · {e.nombre}: {e.estado_texto.toLowerCase()}</span>
            ))}
          </small>
        </div>
        <div className="botones">
          <button className="boton-texto" onClick={() => setAbierto(!abierto)}>{abierto ? 'Ocultar' : 'Ver'}</button>
          {!aviso.leida && <button className="boton-chico boton-borde" onClick={() => onLeer(aviso)}>Ya lo leí</button>}
        </div>
      </div>
      {abierto && <pre className="texto-aviso">{aviso.texto}</pre>}
    </li>
  )
}

export default function Avisos() {
  const [version, setVersion] = useState(0)
  const { datos, error: errorLista } = useConsulta('/api/notificaciones/', version)
  const consultaConfig = useConsulta('/api/notificaciones/configuracion/')
  const [configNueva, setConfigNueva] = useState(null) // la que devuelve la API después de un cambio
  const config = configNueva ?? consultaConfig.datos
  const [error, setError] = useState('')
  const [aviso, setAviso] = useState('')
  const [ocupado, setOcupado] = useState('')
  const [prueba, setPrueba] = useState(null)
  const [token, setToken] = useState('')
  const [miEmail, setMiEmail] = useState(null) // null = todavía no lo tocó: se muestra el guardado
  const [cuenta, setCuenta] = useState(null)
  const [clave, setClave] = useState('')
  const [permiso, setPermiso] = useState(() => (puedeNotificar() ? Notification.permission : 'no'))

  const recargar = () => {
    setVersion((v) => v + 1)
    window.dispatchEvent(new Event(EVENTO_AVISOS))
  }

  // Hace un pedido que cambia algo y muestra cómo salió
  const hacer = async (nombre, pedido, mensaje) => {
    setError('')
    setAviso('')
    setOcupado(nombre)
    try {
      const respuesta = await pedido()
      if (mensaje) setAviso(mensaje)
      return respuesta
    } catch (err) {
      setError(err.message)
      return null
    } finally {
      setOcupado('')
    }
  }

  const leer = async (a) => {
    await hacer('leer', () => api('/api/notificaciones/leer/', { metodo: 'POST', datos: a ? { id: a.id } : {} }))
    recargar()
  }

  const guardar = async (nombre, datos, mensaje) => {
    const nueva = await hacer(nombre, () => api('/api/notificaciones/configuracion/', { metodo: 'PUT', datos }), mensaje)
    if (nueva) setConfigNueva(nueva)
    return nueva
  }

  const guardarBot = async (e) => {
    e.preventDefault()
    if (await guardar('bot', { telegram_token: token.trim() }, 'Se guardó el bot de Telegram del mercado.')) setToken('')
  }

  const quitarBot = () => guardar('bot', { telegram_token: '' }, 'Se quitó el bot de Telegram.')

  const vincular = async () => {
    const nueva = await hacer('vincular', () => api('/api/notificaciones/telegram/vincular/', { metodo: 'POST' }),
      'Tu Telegram quedó vinculado. Te mandamos un mensaje para confirmar.')
    if (nueva) setConfigNueva(nueva)
  }

  const desvincular = async () => {
    const nueva = await hacer('vincular', () => api('/api/notificaciones/telegram/desvincular/', { metodo: 'POST' }),
      'Se desvinculó tu Telegram.')
    if (nueva) setConfigNueva(nueva)
  }

  const guardarCorreo = async (e) => {
    e.preventDefault()
    const datos = { mi_email: (miEmail ?? config.email.mi_email).trim() }
    if (cuenta !== null) datos.email_usuario = cuenta.trim()
    if (clave) datos.email_password = clave
    if (await guardar('correo', datos, 'Se guardaron los datos del correo.')) {
      setClave('')
      setCuenta(null)
      setMiEmail(null)
    }
  }

  const probar = async () => {
    setPrueba(null)
    const r = await hacer('probar', () => api('/api/notificaciones/probar/', { metodo: 'POST' }))
    if (r) setPrueba(r.resultados)
    recargar()
  }

  const pedirPermiso = async () => {
    try {
      setPermiso(await Notification.requestPermission())
    } catch {
      setPermiso('no')
    }
  }

  const avisos = datos?.notificaciones ?? []
  const tg = config?.telegram
  const mail = config?.email

  return (
    <>
      <Encabezado />
      <main className="contenedor">
        <h1>Avisos</h1>
        <p className="subtitulo">
          Todas las noches a las {HORA_CIERRE} el sistema hace solo la caja del día y te la manda: acá, por Telegram y por correo.
        </p>

        {aviso && (
          <p className="mensaje-ok" role="status">
            {aviso} <button className="boton-texto" onClick={() => setAviso('')}>Cerrar</button>
          </p>
        )}
        {(error || errorLista || consultaConfig.error) && (
          <p className="mensaje-error" role="alert">{error || errorLista || consultaConfig.error}</p>
        )}

        <section className="bloque">
          <div className="titulo-con-accion">
            <h2>Mis avisos {datos?.sin_leer > 0 && <small className="texto-suave">({datos.sin_leer} sin leer)</small>}</h2>
            {datos?.sin_leer > 1 && (
              <button className="boton-chico boton-borde" disabled={ocupado === 'leer'} onClick={() => leer(null)}>
                Marcar todos como leídos
              </button>
            )}
          </div>
          {datos === null && !errorLista ? (
            <p className="subtitulo">Cargando…</p>
          ) : avisos.length === 0 ? (
            <p className="texto-suave">Todavía no hay avisos: el primero llega esta noche a las {HORA_CIERRE}, con la caja de hoy.</p>
          ) : (
            <ul className="lista-usuarios">
              {avisos.map((a) => <Aviso key={`${a.id}-${a.leida}`} aviso={a} onLeer={leer} />)}
            </ul>
          )}
        </section>

        {config && (
          <section className="bloque">
            <h2>Por dónde me llegan</h2>
            <p className="texto-suave">
              Los avisos de afuera (Telegram y correo) necesitan que la computadora del mercado esté prendida y con internet
              a las {HORA_CIERRE}. Si no hay internet, el sistema sigue intentando durante varias horas.
            </p>

            <div className="tarjeta canal-aviso">
              <strong>Dentro del sistema <Canal ok>Siempre activo</Canal></strong>
              <p className="texto-suave">Los avisos quedan en esta pantalla y aparece el número en «Avisos», arriba.</p>
              {permiso === 'default' && (
                <button className="boton-chico boton-borde" onClick={pedirPermiso}>
                  Mostrar también una notificación en esta computadora
                </button>
              )}
              {permiso === 'granted' && (
                <small className="texto-suave">Esta computadora muestra una notificación cuando llega un aviso y el sistema está abierto.</small>
              )}
            </div>

            <div className="tarjeta canal-aviso">
              <strong>
                Telegram{' '}
                {tg.vinculado ? <Canal ok>Vinculado{tg.mi_nombre && ` (${tg.mi_nombre})`}</Canal>
                  : <Canal>{tg.configurado ? 'Falta vincular tu Telegram' : 'Falta el bot del mercado'}</Canal>}
              </strong>

              {!tg.configurado ? (
                <form className="formulario-canal" onSubmit={guardarBot} noValidate>
                  <ol className="pasos">
                    <li>En Telegram buscá <b>@BotFather</b> y mandale <b>/newbot</b>.</li>
                    <li>Elegí un nombre (por ejemplo «Caja del Mercado») y un usuario que termine en <b>bot</b>.</li>
                    <li>BotFather te da un <b>token</b> (un texto largo con números y letras). Pegalo acá:</li>
                  </ol>
                  <label>
                    Token del bot
                    <input value={token} autoComplete="off" placeholder="123456789:AA…" onChange={(e) => setToken(e.target.value)} />
                  </label>
                  <button type="submit" disabled={!token.trim() || ocupado === 'bot'}>
                    {ocupado === 'bot' ? 'Comprobando…' : 'Guardar el bot'}
                  </button>
                </form>
              ) : (
                <>
                  <p className="texto-suave">
                    Bot del mercado: <b>@{tg.bot}</b>{' '}
                    <button className="boton-texto" disabled={ocupado === 'bot'} onClick={quitarBot}>Quitar el bot</button>
                  </p>
                  {tg.vinculado ? (
                    <button className="boton-chico boton-borde" disabled={ocupado === 'vincular'} onClick={desvincular}>
                      Desvincular mi Telegram
                    </button>
                  ) : (
                    <>
                      <ol className="pasos">
                        <li>
                          Abrí este enlace en el celular o la computadora donde tenés Telegram:{' '}
                          <a href={tg.enlace} target="_blank" rel="noreferrer">{tg.enlace}</a>
                        </li>
                        <li>Tocá <b>Iniciar</b> (o mandale al bot el mensaje <code>/start {tg.codigo}</code>).</li>
                        <li>Volvé acá y tocá el botón.</li>
                      </ol>
                      <button disabled={ocupado === 'vincular'} onClick={vincular}>
                        {ocupado === 'vincular' ? 'Buscando tu mensaje…' : 'Ya toqué Iniciar: vincular'}
                      </button>
                    </>
                  )}
                </>
              )}
            </div>

            <form className="tarjeta canal-aviso" onSubmit={guardarCorreo} noValidate>
              <strong>
                Correo{' '}
                {mail.configurado && mail.mi_email ? <Canal ok>Activo</Canal>
                  : <Canal>{mail.configurado ? 'Falta tu correo' : 'Falta la cuenta que envía'}</Canal>}
              </strong>
              <label>
                Mi correo <small>(a dónde querés que te llegue)</small>
                <input type="email" value={miEmail ?? mail.mi_email} autoComplete="email" placeholder="vos@gmail.com"
                  onChange={(e) => setMiEmail(e.target.value)} />
              </label>
              <label>
                Cuenta de Gmail del mercado <small>(desde la que manda el sistema; es una sola para todos los dueños)</small>
                <input type="email" value={cuenta ?? mail.usuario} autoComplete="off" placeholder="mercado@gmail.com"
                  onChange={(e) => setCuenta(e.target.value)} />
              </label>
              <label>
                Contraseña de aplicación de esa cuenta{' '}
                <small>{mail.configurado ? '(ya está guardada; escribila solo para cambiarla)' : '(16 letras; no es la contraseña normal)'}</small>
                <input type="password" value={clave} autoComplete="new-password" onChange={(e) => setClave(e.target.value)} />
              </label>
              <small className="texto-suave">
                La contraseña de aplicación se crea en la cuenta de Google del mercado: Seguridad → Verificación en dos pasos
                (hay que activarla) → Contraseñas de aplicaciones.
              </small>
              <button type="submit" disabled={ocupado === 'correo'}>{ocupado === 'correo' ? 'Guardando…' : 'Guardar correo'}</button>
            </form>

            <div className="tarjeta canal-aviso">
              <strong>Probar</strong>
              <p className="texto-suave">Te manda ahora un aviso de prueba por los tres caminos y te dice cómo salió cada uno.</p>
              <button className="boton-borde" disabled={ocupado === 'probar'} onClick={probar}>
                {ocupado === 'probar' ? 'Enviando…' : 'Mandarme un aviso de prueba'}
              </button>
              {prueba && (
                <ul className="resultado-prueba">
                  {prueba.map((r) => (
                    <li key={r.canal}><Canal ok={r.ok}>{r.ok ? 'Bien' : 'No salió'}</Canal> <b>{r.nombre}:</b> {r.detalle}</li>
                  ))}
                </ul>
              )}
            </div>

            {config.dueños.length > 1 && (
              <div className="tarjeta canal-aviso">
                <strong>A quiénes les llega</strong>
                <p className="texto-suave">Cada dueño entra con su cuenta a esta pantalla y vincula su propio Telegram y su correo.</p>
                <ul className="resultado-prueba">
                  {config.dueños.map((d) => (
                    <li key={d.id}>
                      <b>{d.nombre}:</b> <Canal ok>Sistema</Canal> <Canal ok={d.telegram}>Telegram</Canal> <Canal ok={d.email}>Correo</Canal>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>
        )}
      </main>
    </>
  )
}
