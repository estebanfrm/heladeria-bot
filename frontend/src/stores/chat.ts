import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'

import { type Boton, ErrorChat, type MensajeChat, enviarMensaje } from '@/api/chat'

export interface Mensaje {
  id: number
  autor: 'cliente' | 'bot'
  texto: string
  botones: Boton[]
}

interface Guardado {
  sesion: string | null
  mensajes: Mensaje[]
}

/** La conversación sobrevive a una recarga de la página (solo en este navegador). */
const CLAVE = 'heladeria-bot:chat'

function cargar(): Guardado {
  try {
    const crudo = localStorage.getItem(CLAVE)
    if (crudo) return JSON.parse(crudo) as Guardado
  } catch {
    // Almacenamiento bloqueado o dañado: se empieza una conversación nueva
  }
  return { sesion: null, mensajes: [] }
}

export const useChatStore = defineStore('chat', () => {
  const inicial = cargar()
  const sesion = ref<string | null>(inicial.sesion)
  const mensajes = ref<Mensaje[]>(inicial.mensajes)
  const enviando = ref(false)
  const error = ref<string | null>(null)
  const limiteAlcanzado = ref(false)

  /** Solo los botones de la última respuesta del bot se pueden pulsar. */
  const botonesActivos = computed<Boton[]>(() => {
    const ultimo = mensajes.value[mensajes.value.length - 1]
    return ultimo?.autor === 'bot' ? ultimo.botones : []
  })

  watch(
    [sesion, mensajes],
    () => {
      try {
        const guardado: Guardado = { sesion: sesion.value, mensajes: mensajes.value }
        localStorage.setItem(CLAVE, JSON.stringify(guardado))
      } catch {
        // Sin almacenamiento la conversación sigue funcionando, solo no se recuerda
      }
    },
    { deep: true },
  )

  let siguienteId = mensajes.value.reduce((maximo, m) => Math.max(maximo, m.id), 0) + 1

  function agregar(autor: Mensaje['autor'], texto: string, botones: Boton[] = []) {
    mensajes.value.push({ id: siguienteId++, autor, texto, botones })
  }

  async function enviar(cuerpo: Omit<MensajeChat, 'sesion'>, mostrado: string) {
    if (enviando.value || limiteAlcanzado.value) return
    error.value = null
    agregar('cliente', mostrado)
    enviando.value = true
    try {
      const respuesta = await enviarMensaje({ ...cuerpo, sesion: sesion.value ?? undefined })
      sesion.value = respuesta.sesion
      for (const r of respuesta.respuestas) agregar('bot', r.texto, r.botones)
    } catch (e) {
      error.value = e instanceof ErrorChat ? e.message : 'Algo salió mal. Inténtalo de nuevo.'
      if (e instanceof ErrorChat && e.status === 429) limiteAlcanzado.value = true
    } finally {
      enviando.value = false
    }
  }

  async function enviarTexto(texto: string) {
    const limpio = texto.trim()
    if (limpio) await enviar({ texto: limpio }, limpio)
  }

  async function pulsarBoton(boton: Boton) {
    await enviar({ boton: boton.id }, boton.titulo)
  }

  function reiniciar() {
    sesion.value = null
    mensajes.value = []
    error.value = null
    limiteAlcanzado.value = false
  }

  return {
    sesion,
    mensajes,
    enviando,
    error,
    limiteAlcanzado,
    botonesActivos,
    enviarTexto,
    pulsarBoton,
    reiniciar,
  }
})
