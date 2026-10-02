from fastapi import FastAPI

from app.config import settings
from app.menu.schema import cargar_menu

app = FastAPI(title="Heladería Bot", version="0.1.0")

menu = cargar_menu(settings.seed_file)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "env": settings.app_env, "negocio": menu.negocio.nombre}


@app.get("/menu")
def ver_menu():
    """Menú cargado desde el archivo semilla (temporal hasta tener la BD en Fase 1)."""
    return menu
