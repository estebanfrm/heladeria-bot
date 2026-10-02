from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.menu.carga import MenuNoCargado, leer_menu
from app.menu.schema import Menu

app = FastAPI(title="Heladería Bot", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "env": settings.app_env}


@app.get("/menu")
def ver_menu(db: Annotated[Session, Depends(get_db)]) -> Menu:
    """Carta vigente desde la BD: solo productos, opciones, adicionales y medios activos."""
    try:
        return leer_menu(db)
    except MenuNoCargado as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
