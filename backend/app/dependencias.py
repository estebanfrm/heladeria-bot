"""Dependencias compartidas por los canales (inyectables con FastAPI y reemplazables en tests)."""

import logging
from collections.abc import Callable
from functools import lru_cache

from sqlalchemy.orm import Session

from app.canales.whatsapp_api import EnviadorWhatsApp, crear_enviador
from app.config import settings
from app.db import SessionLocal
from app.ia.proveedores import ProveedorIA, ProveedorNoConfigurado, crear_proveedor

logger = logging.getLogger(__name__)


@lru_cache
def get_proveedor() -> ProveedorIA:
    """Proveedor de IA según .env (uno por proceso, reutiliza la conexión HTTP)."""
    try:
        return crear_proveedor(settings)
    except ValueError as e:
        logger.warning("IA no configurada (%s): solo funcionarán los botones", e)
        return ProveedorNoConfigurado(str(e))


@lru_cache
def get_enviador_whatsapp() -> EnviadorWhatsApp:
    return crear_enviador(settings)


def get_sesiones() -> Callable[[], Session]:
    """Fábrica de sesiones para trabajo fuera del request (ej. tareas en segundo plano)."""
    return SessionLocal
