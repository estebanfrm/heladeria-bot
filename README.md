# 🍦 Heladería Bot

Chatbot de pedidos por WhatsApp para una heladería: toma el pedido completo
(menú → productos → opciones → total → dirección → pago), lo envía al personal
con botones de estado y lo registra en un panel.

> Proyecto en desarrollo. Ver la planeación completa en [`PLANEACION.md`](PLANEACION.md).

## Stack

FastAPI · PostgreSQL · SQLAlchemy · Alembic · Vue 3 · Docker · WhatsApp Cloud API · IA intercambiable (Gemini / Groq / Ollama / OpenAI / Anthropic)

**Principio:** la IA interpreta el texto del cliente; el código valida contra el menú y calcula los precios.

## Estructura

```
├── backend/            API FastAPI
│   ├── app/
│   │   ├── config.py       Configuración desde .env
│   │   ├── main.py         Endpoints (/health, /menu) + routers de canales
│   │   ├── models/         Modelos SQLAlchemy (menú, conversaciones, pedidos)
│   │   ├── menu/           Esquema del seed y carga a la BD
│   │   ├── pedidos/        Carrito (reglas y montos) y registro de pedidos
│   │   ├── ia/             IA intercambiable: prompt, proveedores, evaluación
│   │   ├── conversacion/   Motor (máquina de estados) y textos del bot
│   │   └── canales/        Adaptadores: chat web (/chat); WhatsApp en la Fase 2
│   ├── migrations/         Alembic
│   └── tests/
├── frontend/           Panel + chat web (Vue, Fase 2)
├── seeds/
│   └── demo.json       Menú de "Heladería Demo" (datos ficticios de pago)
├── docker-compose.yml
└── .env.example
```

## Correr en local

```bash
cp .env.example .env

# Opción A: todo en Docker
docker compose up --build
# → http://localhost:8000/health y http://localhost:8000/docs

# Opción B: backend local con uv (BD en Docker)
# (si ya tienes otro Postgres en el 5432, cambia DB_PORT y DATABASE_URL en .env)
docker compose up -d db
cd backend
uv sync
uv run alembic upgrade head
uv run python -m app.menu.carga     # carga seeds/demo.json en la BD
uv run uvicorn app.main:app --reload
```

## Probar el bot

Con el backend arriba, abre http://localhost:8000/docs y usa `POST /chat`:

```json
{"texto": "Una copa queso con brownie y fresa y un banana split"}
```

La respuesta trae una `sesion`; mándala en los siguientes mensajes para seguir la misma conversación.
Los botones se envían como `{"sesion": "...", "boton": "confirmar"}`. Para el texto libre hace falta
`IA_API_KEY` (Gemini) en `.env`; sin ella `/health` muestra `"ia": "no configurada"` y solo responden los botones.

## Pruebas

```bash
docker compose up -d db   # los tests de modelos/migraciones usan Postgres real (BD heladeria_test)
cd backend
uv run pytest
uv run ruff check .
```
