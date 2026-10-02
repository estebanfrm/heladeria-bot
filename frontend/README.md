# Frontend — chat web (y panel en la Fase 3)

Vue 3 + Vite + TypeScript + Pinia + Vue Router + Tailwind CSS 4. Gestor: **npm**.

La página de demo (`src/views/DemoView.vue`) presenta el proyecto y trae el widget de chat
(`src/components/ChatWidget.vue`), que habla con `POST /chat` del backend: el mismo motor
que atiende WhatsApp.

## Correr en local

```bash
npm install
cp .env.example .env.local   # VITE_API_URL=http://localhost:8000
npm run dev                  # http://localhost:5173
```

El backend debe estar arriba y permitir el origen en `CORS_ORIGINS` (por defecto `http://localhost:5173`).

## Calidad

```bash
npx vitest run         # tests (formato seguro, store del chat, componente)
npm run type-check
npm run lint           # oxlint + eslint (con --fix)
npx prettier --check src/ index.html
npm run build
```

## Estructura

```
src/api/chat.ts              cliente de POST /chat (errores legibles: límite 429, 503, sin conexión)
src/lib/formato.ts           *negrita* de WhatsApp → HTML, escapando todo antes (seguro para v-html)
src/stores/chat.ts           estado de la conversación (Pinia), persistido en localStorage
src/components/ChatWidget.vue  el chat: burbujas, botones rápidos, aviso de servidor dormido
src/views/DemoView.vue       página del demo para el portafolio
```
