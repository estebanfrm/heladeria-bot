/** Cliente del endpoint POST /chat del backend (canal web del bot). */

export interface Boton {
  id: string
  titulo: string
}

export interface RespuestaBot {
  texto: string
  botones: Boton[]
}

export interface RespuestaChat {
  sesion: string
  respuestas: RespuestaBot[]
}

export interface MensajeChat {
  sesion?: string
  texto?: string
  boton?: string
}

export const API_URL = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '')

export class ErrorChat extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message)
    this.name = 'ErrorChat'
  }
}

export async function enviarMensaje(cuerpo: MensajeChat): Promise<RespuestaChat> {
  let respuesta: Response
  try {
    respuesta = await fetch(`${API_URL}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(cuerpo),
    })
  } catch {
    throw new ErrorChat('No pudimos conectar con el bot. Revisa tu conexión e inténtalo de nuevo.')
  }
  if (!respuesta.ok) {
    const detalle = await leerDetalle(respuesta)
    throw new ErrorChat(
      detalle ?? `El bot no pudo responder (error ${respuesta.status}).`,
      respuesta.status,
    )
  }
  return (await respuesta.json()) as RespuestaChat
}

/** Mensaje legible del backend ({"detail": "..."}); los errores de validación traen una lista. */
async function leerDetalle(respuesta: Response): Promise<string | null> {
  try {
    const datos = await respuesta.json()
    return typeof datos?.detail === 'string' ? datos.detail : null
  } catch {
    return null
  }
}
