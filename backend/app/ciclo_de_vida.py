"""Temporizador del servidor: cierre persistente y avisos de WhatsApp reintentables."""

import asyncio
import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.canales.whatsapp_api import EnviadorNoConfigurado, EnviadorWhatsApp
from app.config import settings
from app.conversacion import mensajes
from app.conversacion.inactividad import (
    ESTADOS_CERRABLES,
    ahora_utc,
    cerrar_si_inactiva,
    ventana_whatsapp_abierta,
)
from app.dependencias import get_enviador_whatsapp, get_sesiones
from app.enums import Canal, EstadoConversacion
from app.models import Conversacion, Mensaje

logger = logging.getLogger(__name__)


def procesar_cierres(
    sesiones: Callable[[], Session],
    enviador: EnviadorWhatsApp,
    *,
    ahora: datetime | None = None,
) -> dict[str, int]:
    momento_fijo = ahora
    ahora = ahora or ahora_utc()
    limite = ahora - timedelta(minutes=settings.chat_inactivity_minutes)
    ultima = (
        select(func.max(Mensaje.creado))
        .where(Mensaje.conversacion_id == Conversacion.id)
        .correlate(Conversacion)
        .scalar_subquery()
    )
    with sesiones() as db:
        candidatos = db.scalars(
            select(Conversacion.id)
            .where(
                Conversacion.estado.in_(ESTADOS_CERRABLES),
                Conversacion.actualizado <= limite,
                func.coalesce(ultima, Conversacion.creado) <= limite,
            )
            .order_by(Conversacion.id)
            .limit(100)
        ).all()
    cerradas = 0
    for id_conv in candidatos:
        try:
            with sesiones() as db:
                conv = db.scalar(
                    select(Conversacion)
                    .where(Conversacion.id == id_conv)
                    .with_for_update(skip_locked=True)
                )
                if conv is not None and cerrar_si_inactiva(db, conv, ahora=ahora):
                    db.commit()
                    cerradas += 1
        except Exception:
            logger.exception("No se pudo cerrar la conversación %s", id_conv)

    avisos = 0
    if isinstance(enviador, EnviadorNoConfigurado):
        return {"cerradas": cerradas, "avisos": avisos}
    with sesiones() as db:
        pendientes = db.scalars(
            select(Conversacion.id)
            .where(
                Conversacion.estado == EstadoConversacion.CANCELADA,
                Conversacion.canal == Canal.WHATSAPP,
                Conversacion.contexto_json["aviso_cierre_pendiente"].as_boolean().is_(True),
            )
            .order_by(Conversacion.id)
            .limit(100)
        ).all()
    for id_conv in pendientes:
        try:
            with sesiones() as db:
                conv = db.scalar(
                    select(Conversacion)
                    .where(Conversacion.id == id_conv)
                    .with_for_update(skip_locked=True)
                )
                if conv is None or conv.estado is not EstadoConversacion.CANCELADA:
                    continue
                if not conv.contexto_json.get("aviso_cierre_pendiente"):
                    continue
                # Mantener el bloqueo impide enviar un aviso viejo tras abrir un chat nuevo.
                if ventana_whatsapp_abierta(db, conv, momento_fijo or ahora_utc()):
                    respuesta = mensajes.chat_cerrado(conv.contexto_json["minutos_cierre"])
                    enviador.enviar(conv.id_externo, respuesta)
                    avisos += 1
                conv.contexto_json["aviso_cierre_pendiente"] = False
                db.commit()
        except Exception:
            # El cierre ya está guardado. El aviso pendiente se reintenta en el próximo ciclo.
            logger.exception("No se pudo enviar el aviso de cierre de la conversación %s", id_conv)
    return {"cerradas": cerradas, "avisos": avisos}


async def vigilar_inactividad(detener: asyncio.Event) -> None:
    while not detener.is_set():
        try:
            await asyncio.to_thread(procesar_cierres, get_sesiones(), get_enviador_whatsapp())
        except Exception:
            logger.exception("Falló el ciclo de cierre de conversaciones")
        try:
            await asyncio.wait_for(detener.wait(), timeout=settings.chat_inactivity_poll_seconds)
        except TimeoutError:
            pass


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if not settings.chat_inactivity_worker_enabled:
        yield
        return
    detener = asyncio.Event()
    tarea = asyncio.create_task(vigilar_inactividad(detener))
    logger.info("Cierre por inactividad activo: %s minutos", settings.chat_inactivity_minutes)
    try:
        yield
    finally:
        detener.set()
        await tarea
