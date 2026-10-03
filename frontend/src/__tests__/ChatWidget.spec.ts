import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import ChatWidget from '@/components/ChatWidget.vue'

type Fetch = typeof globalThis.fetch

function respuestaBot(texto: string, botones: { id: string; titulo: string }[] = []) {
  return new Response(
    JSON.stringify({ sesion: 'sesion-de-prueba-1', respuestas: [{ texto, botones }] }),
    { status: 200, headers: { 'Content-Type': 'application/json' } },
  )
}

beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ChatWidget', () => {
  it('envía con Enter y muestra la respuesta con formato y botones', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn<Fetch>()
        .mockResolvedValue(
          respuestaBot('*Total: $24.000*', [{ id: 'confirmar', titulo: 'Confirmar' }]),
        ),
    )
    const widget = mount(ChatWidget)

    await widget.find('textarea').setValue('una copa queso')
    await widget.find('textarea').trigger('keydown', { key: 'Enter' })
    await flushPromises()

    const mensajes = widget.findAll('li[data-autor]')
    expect(mensajes.map((m) => m.attributes('data-autor'))).toEqual(['cliente', 'bot'])
    expect(mensajes[1]!.html()).toContain('<strong>Total: $24.000</strong>')
    expect(widget.find('textarea').element.value).toBe('')
    expect(widget.findAll('button').map((b) => b.text())).toContain('Confirmar')
  })

  it('pulsar un botón lo envía al bot', async () => {
    const fetch = vi
      .fn<Fetch>()
      .mockResolvedValueOnce(
        respuestaBot('¿Qué se te antoja?', [{ id: 'menu', titulo: 'Ver menú' }]),
      )
      .mockResolvedValueOnce(respuestaBot('🍦 *Menú de Heladería Demo*'))
    vi.stubGlobal('fetch', fetch)
    const widget = mount(ChatWidget)
    await widget.find('textarea').setValue('hola')
    await widget.find('form').trigger('submit')
    await flushPromises()

    const verMenu = widget.findAll('button').find((b) => b.text() === 'Ver menú')!
    await verMenu.trigger('click')
    await flushPromises()

    expect(JSON.parse(fetch.mock.calls[1]![1]!.body as string)).toMatchObject({ boton: 'menu' })
    expect(widget.text()).toContain('Menú de Heladería Demo')
  })

  it('no permite enviar mensajes vacíos', async () => {
    const fetch = vi.fn<Fetch>()
    vi.stubGlobal('fetch', fetch)
    const widget = mount(ChatWidget)

    await widget.find('textarea').setValue('   ')
    await widget.find('form').trigger('submit')

    expect(fetch).not.toHaveBeenCalled()
    expect(widget.find('button[type="submit"]').attributes('disabled')).toBeDefined()
  })
})
