# Build desde la RAÍZ del repo:  docker build -f backend/Dockerfile .
# La imagen replica la estructura del repo en /app (backend/ y seeds/), igual que en desarrollo.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app/backend
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/backend/.venv/bin:$PATH"

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --no-dev --no-install-project

COPY backend/app ./app
COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
# Solo el menú ficticio del demo. Los datos reales (seeds/heladeria.json) NUNCA van en la imagen:
# en producción se montan como volumen en /app/seeds y se elige con SEED_FILE.
COPY seeds/demo.json /app/seeds/demo.json

EXPOSE 8000
# Migraciones pendientes → menú semilla (solo si trae versión nueva) → API
CMD ["sh", "-c", "alembic upgrade head && python -m app.menu.carga --auto && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
