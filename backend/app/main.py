from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.canales import web
from app.config import settings
from app.db import get_db
from app.ia.proveedores import ProveedorNoConfigurado
from app.menu.carga import MenuNoCargado, leer_menu
from app.menu.schema import Menu

app = FastAPI(title="Heladería Bot", version="0.1.0")
app.include_router(web.router)


@app.exception_handler(MenuNoCargado)
def menu_no_cargado(_request: Request, error: MenuNoCargado) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(error)})


@app.get("/health")
def health() -> dict:
    proveedor = web.get_proveedor()
    if isinstance(proveedor, ProveedorNoConfigurado):
        ia = f"no configurada: {proveedor.motivo}"
    else:
        ia = f"{settings.ia_provider} / {settings.ia_model}"
    return {"status": "ok", "env": settings.app_env, "ia": ia}


@app.get("/menu")
def ver_menu(db: Annotated[Session, Depends(get_db)]) -> Menu:
    """Carta vigente desde la BD: solo productos, opciones, adicionales y medios activos."""
    return leer_menu(db)
