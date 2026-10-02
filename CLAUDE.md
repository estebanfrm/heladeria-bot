# Heladería Bot — contexto para Claude Code

Chatbot de pedidos por WhatsApp para una heladería de Cali que hoy atiende manualmente.
Proyecto de portafolio de Esteban (dev full stack junior: Vue, FastAPI, PostgreSQL, Docker).
La planeación completa y todas las decisiones están en `PLANEACION.md` — léela antes de cambios grandes.

## Forma de trabajo

- Responde en **español**, estilo directo, **paso a paso**: una fase o tarea a la vez, y muestra qué cambió.
- Corre lint y tests antes de dar algo por terminado.
- Al terminar una tarea, márcala `[x]` en la sección 11 de `PLANEACION.md`.
- Entorno: **Windows**. Usa PowerShell o Git Bash; rutas con cuidado.

## Reglas del proyecto (no negociables)

1. **"La IA interpreta, el código decide"**: el LLM solo convierte texto libre → JSON con IDs del menú. Validación, reglas, adicionales y precios los calcula el código. Nunca precios desde la IA.
2. **Todo configurable por `.env`** (ver `.env.example` y `backend/app/config.py`). Nada de credenciales en el código.
3. **IA intercambiable** detrás de una interfaz (`IA_PROVIDER`: gemini | groq | ollama | openai | anthropic). Demo con capa gratis.
4. **Canales como adaptadores** (WhatsApp Cloud API oficial + chat web) sobre un mismo motor de conversación.
5. **Pagos detrás de `ProveedorPago`**. MVP = nivel 1 (manual): el bot envía cuenta + monto, reenvía el comprobante al personal y este confirma con botón.
6. **Demo con datos ficticios**: "Heladería Demo" y cuentas falsas. Nunca poner números de cuenta reales en `seeds/demo.json` (hay un test que lo verifica). Datos reales irían en `seeds/heladeria.json` (en .gitignore).
7. Solo **WhatsApp Cloud API oficial** (nada de whatsapp-web.js/Baileys).
8. Proyecto **migrable**: Docker, PostgreSQL estándar + Alembic, nada exclusivo de un proveedor.

## Stack

- Backend: Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic 2, pydantic-settings, httpx, pytest, ruff. Gestor: **uv**.
- BD: PostgreSQL 16 (Docker).
- Frontend (Fase 2): Vue 3 + Vite + TypeScript, Pinia, Vue Router, Tailwind.
- Despliegue demo: Render (backend), Neon (BD), Vercel (frontend).

## Estructura

```
backend/app/config.py        configuración desde .env (lee el .env de la raíz del repo)
backend/app/main.py          endpoints (/health, /menu desde la BD)
backend/app/enums.py         valores cerrados del dominio (estados, canal, tipo de grupo…)
backend/app/db.py            Base SQLAlchemy, engine, SessionLocal, get_db
backend/app/models/          modelos de BD: menu.py, conversaciones.py, pedidos.py
backend/app/menu/schema.py   modelos Pydantic + validación del menú semilla
backend/app/menu/carga.py    seed → BD (sincroniza por codigo) y BD → Menu (carta vigente)
backend/app/pedidos/carrito.py  ItemSolicitado (lo que entrega la IA: solo códigos) → validación,
                             faltantes, problemas y montos (precios del Menu, nunca de la IA)
backend/app/ia/              servicio de IA: prompt (menú sin precios) → proveedor → Interpretacion
                             validada; proveedores.py (compatible OpenAI + falso), casos.py (chat real)
backend/migrations/          Alembic (env.py toma DATABASE_URL de settings)
backend/tests/               pytest (conftest.py: BD heladeria_test en Postgres real)
seeds/demo.json              menú completo (26 productos, 11 sabores, adicionales, medios de pago ficticios)
docker-compose.yml           db (postgres) + backend (build con contexto = raíz del repo)
.dockerignore                lista blanca: solo backend + seeds/demo.json entran a la imagen
```

Imagen Docker: replica el repo en `/app`; trae solo `seeds/demo.json`. Datos reales
(`seeds/heladeria.json`) se montan como volumen y se eligen con `SEED_FILE` (relativo a la raíz del repo).

**Ojo (equipo de Esteban):** hay un PostgreSQL 18 nativo de Windows ocupando el 5432. El `.env` local usa
`DB_PORT=5433` y `DATABASE_URL=...@localhost:5433/...`. En CI y Docker todo sigue en 5432.

## Comandos

```bash
# desde backend/
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run uvicorn app.main:app --reload        # http://localhost:8000/docs
uv run alembic upgrade head                 # aplicar migraciones
uv run python -m app.menu.carga             # aplicar SEED_FILE a la BD (--auto: solo si hay versión nueva)
uv run python -m app.ia.evaluar             # evalúa el proveedor de IA de .env con el chat real (necesita API key)
uv run alembic revision --autogenerate -m "describe el cambio"   # tras cambiar un modelo (revisar el archivo generado)

# desde la raíz
docker compose up -d db                     # solo la BD
docker compose up --build                   # todo
docker build -f backend/Dockerfile .        # solo la imagen, como en Render (contexto = raíz)
```

## Dominio del menú (resumen)

- Productos con `selecciones`: cada una es un grupo de opciones + cantidad (ej. copa queso = 2 sabores + 1 salsa + 1 topping; banana split = 3 sabores + 1 salsa + 1 topping). Los sabores **pueden repetirse**.
- Las listas de salsas/toppings **varían por producto** (`salsas_waffle`, `salsas_base`, `salsas_generales`, etc.).
- Adicionales con precio fijo; algunos exigen elegir del grupo (ej. topping adicional → qué topping).
- Caso de prueba real: copa queso (brownie, fresa · frutos rojos · maní) + banana split (brownie, vainilla chips, brownie · frutos rojos · oreo) = **$24.000**.
- `_pendientes` en `demo.json` lista lo que falta confirmar con la heladería.

## Estado actual

- ✅ Fase 0: estructura del repo, menú semilla validado. Repo: https://github.com/estebanfrm/heladeria-bot
- 🔄 **Fase 1 — Núcleo (sin WhatsApp)**, en este orden:
  1. ✅ Modelos SQLAlchemy + migraciones `0001`–`0002` (sección 8 de `PLANEACION.md`).
  2. ✅ Carga del seed a la BD; `/menu` lee de Postgres.
  3. ✅ Carrito y reglas (`app/pedidos/carrito.py`): caso real de $24.000.
  4. ✅ Servicio de IA (`app/ia/`): gemini | groq | ollama | openai vía API compatible con OpenAI;
     anthropic pendiente. Falta elegir Gemini vs Groq con `app.ia.evaluar` (requiere API keys). 68 tests.
  5. ⏭️ **Siguiente:** motor de conversación (máquina de estados, sección 7).
  6. Endpoint `/chat` de prueba + tests con los mensajes del chat real.
