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
│   │   ├── config.py   Configuración desde .env
│   │   ├── main.py     Endpoints
│   │   └── menu/       Esquema y validación del menú
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
docker compose up -d db
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

## Pruebas

```bash
cd backend
uv run pytest
uv run ruff check .
```
