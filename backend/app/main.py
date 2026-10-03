from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.canales import web, whatsapp
from app.ciclo_de_vida import lifespan
from app.config import settings
from app.db import get_db
from app.dependencias import get_proveedor
from app.ia.proveedores import ProveedorNoConfigurado
from app.menu.carga import MenuNoCargado, leer_menu
from app.menu.schema import Menu

app = FastAPI(title="Heladería Bot", version="0.1.0", lifespan=lifespan)
app.include_router(web.router)
app.include_router(whatsapp.router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,  # CORS_ORIGINS en .env
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(MenuNoCargado)
def menu_no_cargado(_request: Request, error: MenuNoCargado) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(error)})


@app.get("/health")
def health() -> dict:
    proveedor = get_proveedor()
    if isinstance(proveedor, ProveedorNoConfigurado):
        ia = f"no configurada: {proveedor.motivo}"
    else:
        ia = f"{settings.ia_provider} / {settings.ia_model}"
    return {"status": "ok", "env": settings.app_env, "ia": ia}


@app.get("/menu")
def ver_menu(db: Annotated[Session, Depends(get_db)]) -> Menu:
    """Carta vigente desde la BD: solo productos, opciones, adicionales y medios activos."""
    return leer_menu(db)
