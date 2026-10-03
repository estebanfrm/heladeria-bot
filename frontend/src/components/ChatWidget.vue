<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'

import { formatearMensaje } from '@/lib/formato'
import { useChatStore } from '@/stores/chat'

const MAX_CARACTERES = 500 // el backend rechaza mensajes más largos
const AVISO_LENTO_MS = 4000 // Render gratis "se duerme": la primera respuesta puede tardar

const chat = useChatStore()
const { mensajes, enviando, error, limiteAlcanzado, botonesActivos } = storeToRefs(chat)

const texto = ref('')
const lista = ref<HTMLElement | null>(null)
const lento = ref(false)
let temporizador: ReturnType<typeof setTimeout> | undefined

watch(enviando, (activo) => {
  clearTimeout(temporizador)
  lento.value = false
  if (activo) temporizador = setTimeout(() => (lento.value = true), AVISO_LENTO_MS)
})
onBeforeUnmount(() => clearTimeout(temporizador))

// Siempre mostrar lo último
watch(
  () => [mensajes.value.length, enviando.value],
  async () => {
    await nextTick()
    if (lista.value) lista.value.scrollTop = lista.value.scrollHeight
  },
  { immediate: true },
)

async function enviar() {
  const mensaje = texto.value
  if (!mensaje.trim() || enviando.value) return
  texto.value = ''
  await chat.enviarTexto(mensaje)
}
</script>

<template>
  <section
    class="flex h-[34rem] max-h-[85dvh] flex-col overflow-hidden rounded-2xl border border-stone-200 bg-white shadow-xl"
    aria-label="Chat con el bot de la heladería"
  >
    <header class="flex items-center gap-3 bg-rose-600 px-4 py-3 text-white">
      <span
        aria-hidden="true"
        class="grid size-9 place-items-center rounded-full bg-white/20 text-lg"
        >🍦</span
      >
      <div class="min-w-0 flex-1">
        <h2 class="leading-tight font-semibold">Heladería Demo</h2>
        <p class="text-xs text-rose-100">Bot de pedidos · datos ficticios</p>
      </div>
      <button
        type="button"
        class="rounded-lg px-2 py-1 text-xs font-medium text-rose-50 hover:bg-white/15"
        @click="chat.reiniciar()"
      >
        Nueva conversación
      </button>
    </header>

    <ol
      ref="lista"
      class="flex-1 space-y-2 overflow-y-auto bg-stone-50 px-3 py-4"
      aria-live="polite"
    >
      <li v-if="!mensajes.length" class="mx-auto max-w-xs py-8 text-center text-sm text-stone-500">
        Escríbele como lo harías por WhatsApp, por ejemplo:
        <em>«una copa queso con brownie y fresa»</em>.
      </li>
      <li
        v-for="m in mensajes"
        :key="m.id"
        class="flex"
        :class="m.autor === 'cliente' ? 'justify-end' : 'justify-start'"
        :data-autor="m.autor"
      >
        <!-- Seguro: formatearMensaje escapa todo el HTML antes de agregar la negrita -->
        <!-- eslint-disable-next-line vue/no-v-html -->
        <p
          class="max-w-[85%] rounded-2xl px-3 py-2 text-sm break-words whitespace-pre-line shadow-sm"
          :class="
            m.autor === 'cliente'
              ? 'rounded-br-sm bg-rose-600 text-white'
              : 'rounded-bl-sm bg-white text-stone-800'
          "
          v-html="formatearMensaje(m.texto)"
        />
      </li>
      <li v-if="enviando" class="flex justify-start">
        <p class="rounded-2xl rounded-bl-sm bg-white px-3 py-2 text-sm text-stone-400 shadow-sm">
          escribiendo…
        </p>
      </li>
    </ol>

    <div
      v-if="botonesActivos.length && !enviando"
      class="flex flex-wrap gap-2 border-t border-stone-200 bg-white px-3 py-2"
    >
      <button
        v-for="boton in botonesActivos"
        :key="boton.id"
        type="button"
        class="rounded-full border border-rose-300 px-3 py-1 text-xs font-medium text-rose-700 hover:bg-rose-50"
        @click="chat.pulsarBoton(boton)"
      >
        {{ boton.titulo }}
      </button>
    </div>

    <p v-if="lento" class="bg-amber-50 px-3 py-2 text-xs text-amber-800">
      El servidor gratuito se está despertando; la primera respuesta puede tardar hasta un minuto…
    </p>
    <p v-if="error" role="alert" class="bg-red-50 px-3 py-2 text-xs text-red-700">{{ error }}</p>

    <form
      class="flex items-end gap-2 border-t border-stone-200 bg-white p-3"
      @submit.prevent="enviar"
    >
      <label for="mensaje" class="sr-only">Mensaje</label>
      <textarea
        id="mensaje"
        v-model="texto"
        rows="1"
        :maxlength="MAX_CARACTERES"
        :disabled="limiteAlcanzado"
        placeholder="Escribe tu pedido…"
        class="max-h-28 flex-1 resize-none rounded-xl border border-stone-300 px-3 py-2 text-sm focus:border-rose-500 focus:ring-2 focus:ring-rose-200 focus:outline-none disabled:bg-stone-100"
        @keydown.enter.exact.prevent="enviar"
      />
      <button
        type="submit"
        :disabled="enviando || limiteAlcanzado || !texto.trim()"
        class="rounded-xl bg-rose-600 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-700 disabled:opacity-40"
      >
        Enviar
      </button>
    </form>
  </section>
</template>
