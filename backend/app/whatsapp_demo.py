"""Entrada para el túnel de pruebas: publica únicamente el webhook de WhatsApp.

Ejecutar desde backend: uv run uvicorn app.whatsapp_demo:app --host 127.0.0.1 --port 8001
El chat web y la documentación continúan en app.main, en el puerto 8000.
"""

from fastapi import FastAPI

from app.canales.whatsapp import router
from app.ciclo_de_vida import lifespan

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.include_router(router)
