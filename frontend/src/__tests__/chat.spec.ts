import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useChatStore } from '@/stores/chat'

const RESUMEN = {
  sesion: 'sesion-de-prueba-1',
  respuestas: [
    {
      texto: '📝 *Tu pedido:*\n*Total: $24.000*',
      botones: [
        { id: 'confirmar', titulo: 'Confirmar' },
        { id: 'agregar', titulo: 'Agregar algo' },
      ],
    },
  ],
}

type Fetch = typeof globalThis.fetch

function responder(cuerpo: unknown, status = 200) {
  return vi.fn<Fetch>().mockResolvedValue(
    new Response(JSON.stringify(cuerpo), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
}

beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('store del chat', () => {
  it('envía el texto, guarda la sesión y muestra las respuestas con sus botones', async () => {
    const fetch = responder(RESUMEN)
    vi.stubGlobal('fetch', fetch)
    const chat = useChatStore()

    await chat.enviarTexto('  una copa queso y un banana split  ')

    const [url, opciones] = fetch.mock.calls[0]!
    expect(url).toBe('http://localhost:8000/chat')
    expect(JSON.parse(opciones!.body as string)).toEqual({
      texto: 'una copa queso y un banana split',
    })
    expect(chat.sesion).toBe('sesion-de-prueba-1')
    expect(chat.mensajes.map((m) => m.autor)).toEqual(['cliente', 'bot'])
    expect(chat.botonesActivos.map((b) => b.id)).toEqual(['confirmar', 'agregar'])
  })

  it('un botón se envía por id, se muestra con su título y reutiliza la sesión', async () => {
    vi.stubGlobal('fetch', responder(RESUMEN))
    const chat = useChatStore()
    await chat.enviarTexto('hola')

    const fetch = responder({ sesion: 'sesion-de-prueba-1', respuestas: [] })
    vi.stubGlobal('fetch', fetch)
    await chat.pulsarBoton({ id: 'confirmar', titulo: 'Confirmar' })

    expect(JSON.parse(fetch.mock.calls[0]![1]!.body as string)).toEqual({
      boton: 'confirmar',
      sesion: 'sesion-de-prueba-1',
    })
    expect(chat.mensajes[chat.mensajes.length - 1]).toMatchObject({
      autor: 'cliente',
      texto: 'Confirmar',
    })
    expect(chat.botonesActivos).toEqual([]) // los botones viejos ya no se pueden pulsar
  })

  it('al llegar al límite del demo muestra el aviso del backend y bloquea el envío', async () => {
    vi.stubGlobal('fetch', responder({ detail: 'Llegaste al límite de 20 mensajes' }, 429))
    const chat = useChatStore()

    await chat.enviarTexto('otro mensaje')

    expect(chat.error).toBe('Llegaste al límite de 20 mensajes')
    expect(chat.limiteAlcanzado).toBe(true)
  })

  it('sin conexión muestra un error claro', async () => {
    vi.stubGlobal('fetch', vi.fn<Fetch>().mockRejectedValue(new TypeError('Failed to fetch')))
    const chat = useChatStore()

    await chat.enviarTexto('hola')

    expect(chat.error).toMatch(/No pudimos conectar con el bot/)
    expect(chat.enviando).toBe(false)
  })

  it('la conversación sobrevive a una recarga y "Nueva conversación" la borra', async () => {
    vi.stubGlobal('fetch', responder(RESUMEN))
    await useChatStore().enviarTexto('hola')

    setActivePinia(createPinia()) // como recargar la página
    const recargado = useChatStore()
    expect(recargado.sesion).toBe('sesion-de-prueba-1')
    expect(recargado.mensajes).toHaveLength(2)

    recargado.reiniciar()
    expect(recargado.sesion).toBeNull()
    expect(recargado.mensajes).toEqual([])
  })
})
