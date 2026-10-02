<script setup lang="ts">
import { storeToRefs } from 'pinia'

import ChatWidget from '@/components/ChatWidget.vue'
import { useChatStore } from '@/stores/chat'

const chat = useChatStore()
const { enviando, limiteAlcanzado } = storeToRefs(chat)

/** En móvil el chat queda debajo del texto: llevar al visitante hasta él. */
function irAlChat() {
  document.getElementById('chat')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

async function probar(ejemplo: string) {
  irAlChat()
  await chat.enviarTexto(ejemplo)
}

const ejemplos = [
  'Una copa queso con brownie y fresa y un banana split',
  'Dos conos de una bola, uno de fresa y otro de lulo',
  '¿Me muestras el menú?',
]
</script>

<template>
  <main
    class="mx-auto grid min-h-dvh max-w-6xl items-center gap-10 px-4 py-10 lg:grid-cols-[1fr_26rem]"
  >
    <section>
      <p class="text-sm font-semibold tracking-wide text-rose-600 uppercase">
        Proyecto de portafolio
      </p>
      <h1 class="mt-2 text-4xl font-bold tracking-tight text-stone-900 sm:text-5xl">
        Un bot que toma pedidos de helado por WhatsApp
      </h1>
      <p class="mt-4 text-lg text-stone-600">
        Escríbele como a cualquier heladería: arma tu pedido, te pregunta en un solo mensaje lo que
        falta y calcula el total. Este chat usa el mismo motor que atiende WhatsApp.
      </p>
      <a
        href="#chat"
        class="mt-5 inline-block rounded-xl bg-rose-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-rose-700 lg:hidden"
        @click.prevent="irAlChat"
        >Probar el bot ↓</a
      >

      <ul class="mt-6 space-y-3 text-stone-700">
        <li>
          🧠 <strong>La IA interpreta, el código decide:</strong> la IA solo traduce tu mensaje a
          códigos del menú; precios, reglas y totales los calcula el backend.
        </li>
        <li>🍨 Reglas por producto: cada uno tiene sus sabores, salsas y toppings.</li>
        <li>📲 Canales como adaptadores: chat web y WhatsApp Cloud API sobre el mismo motor.</li>
      </ul>

      <div class="mt-8">
        <p class="text-sm font-medium text-stone-500">Prueba con:</p>
        <div class="mt-2 flex flex-wrap gap-2">
          <button
            v-for="ejemplo in ejemplos"
            :key="ejemplo"
            type="button"
            :disabled="enviando || limiteAlcanzado"
            class="rounded-full bg-white px-3 py-1.5 text-left text-sm text-stone-700 shadow-sm ring-1 ring-stone-200 hover:ring-rose-300 disabled:opacity-50"
            @click="probar(ejemplo)"
          >
            «{{ ejemplo }}»
          </button>
        </div>
      </div>

      <p class="mt-8 text-sm text-stone-500">
        Datos ficticios («Heladería Demo»). FastAPI · PostgreSQL · Vue · IA intercambiable ·
        <a
          href="https://github.com/estebanfrm/heladeria-bot"
          class="font-medium text-rose-700 underline underline-offset-2"
          target="_blank"
          rel="noopener"
          >código en GitHub</a
        >
      </p>
    </section>

    <ChatWidget id="chat" class="scroll-mt-4" />
  </main>
</template>
