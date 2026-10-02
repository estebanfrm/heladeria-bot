"""Canal: WhatsApp Cloud API (webhook de Meta).

- GET  /webhook/whatsapp  verificación del webhook (hub.challenge) con WA_VERIFY_TOKEN.
- POST /webhook/whatsapp  mensajes entrantes. Se valida la firma X-Hub-Signature-256 con
  WA_APP_SECRET, se responde 200 de inmediato (Meta reintenta si tarda) y el mensaje se procesa
  en segundo plano: motor de conversación → respuestas → Cloud API.

Es un adaptador delgado, igual que el del chat web: traduce el formato de Meta a `Entrada`.
"""

import hashlib
import hmac
import json
import logging
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.canales.whatsapp_api import EnviadorWhatsApp, ErrorWhatsApp
from app.config import settings
from app.conversacion.motor import Entrada, Motor
from app.dependencias import get_enviador_whatsapp, get_proveedor, get_sesiones
from app.enums import Canal
from app.ia.proveedores import ProveedorIA
from app.models import Mensaje

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook/whatsapp", tags=["WhatsApp"])


@router.get("", response_class=PlainTextResponse)
def verificar(
    modo: Annotated[str, Query(alias="hub.mode")] = "",
    token: Annotated[str, Query(alias="hub.verify_token")] = "",
    desafio: Annotated[str, Query(alias="hub.challenge")] = "",
) -> str:
    """Meta llama aquí al registrar el webhook; se responde el desafío si el token coincide."""
    esperado = settings.wa_verify_token
    if modo == "subscribe" and esperado and hmac.compare_digest(token, esperado):
        return desafio
    raise HTTPException(status_code=403, detail="Token de verificación inválido")


@router.post("")
async def recibir(
    request: Request,
    tareas: BackgroundTasks,
    sesiones: Annotated[Callable[[], Session], Depends(get_sesiones)],
    proveedor: Annotated[ProveedorIA, Depends(get_proveedor)],
    enviador: Annotated[EnviadorWhatsApp, Depends(get_enviador_whatsapp)],
) -> dict:
    cuerpo = await request.body()
    if not firma_valida(cuerpo, request.headers.get("X-Hub-Signature-256"), settings.wa_app_secret):
        raise HTTPException(status_code=403, detail="Firma inválida")
    try:
        datos = json.loads(cuerpo)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="JSON inválido") from e

    entradas = extraer_entradas(datos)
    if entradas:
        tareas.add_task(procesar_entradas, entradas, sesiones, proveedor, enviador)
    return {"recibidos": len(entradas)}


def firma_valida(cuerpo: bytes, firma: str | None, secreto: str) -> bool:
    """X-Hub-Signature-256 = "sha256=" + HMAC-SHA256(cuerpo, App Secret). Sin secreto: rechazo."""
    if not secreto or not firma or not firma.startswith("sha256="):
        return False
    esperada = hmac.new(secreto.encode(), cuerpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(firma.removeprefix("sha256="), esperada)


def extraer_entradas(datos: dict[str, Any]) -> list[Entrada]:
    """Payload de Meta → mensajes para el motor (los avisos de entregado/leído se ignoran)."""
    entradas = []
    for entrada in datos.get("entry", []):
        for cambio in entrada.get("changes", []):
            valor = cambio.get("value", {})
            nombres = {
                c.get("wa_id"): c.get("profile", {}).get("name") for c in valor.get("contacts", [])
            }
            for mensaje in valor.get("messages", []):
                try:
                    entradas.append(_a_entrada(mensaje, nombres))
                except (KeyError, TypeError):
                    logger.warning("Mensaje de WhatsApp con formato inesperado: %s", mensaje)
    return entradas


def _a_entrada(mensaje: dict[str, Any], nombres: dict[str, str | None]) -> Entrada:
    telefono = mensaje["from"]
    base: dict[str, Any] = {
        "canal": Canal.WHATSAPP,
        "id_externo": telefono,
        "nombre": nombres.get(telefono),
        "id_mensaje": mensaje.get("id"),
    }
    match mensaje.get("type"):
        case "text":
            return Entrada(texto=mensaje["text"]["body"], **base)
        case "interactive":  # respuesta a botones o a una lista
            interactivo = mensaje["interactive"]
            respuesta = interactivo.get("button_reply") or interactivo["list_reply"]
            return Entrada(boton=respuesta["id"], **base)
        case "button":  # botón de una plantilla
            return Entrada(boton=mensaje["button"]["payload"], **base)
        case "image":  # ej. el comprobante de pago; el id permite descargarla o reenviarla
            imagen = mensaje["image"]
            return Entrada(
                texto=imagen.get("caption", ""), media_url=f"whatsapp:{imagen['id']}", **base
            )
        case _:  # audio, sticker, ubicación…: el motor responde que solo lee texto
            return Entrada(**base)


def procesar_entradas(
    entradas: list[Entrada],
    sesiones: Callable[[], Session],
    proveedor: ProveedorIA,
    enviador: EnviadorWhatsApp,
) -> None:
    """Se ejecuta después de responder 200 a Meta. Cada mensaje, en su propia transacción."""
    for entrada in entradas:
        with sesiones() as db:
            if entrada.id_mensaje and db.scalar(
                select(Mensaje.id).where(Mensaje.id_externo == entrada.id_mensaje)
            ):
                logger.info(
                    "Mensaje %s repetido (reintento de Meta): se ignora", entrada.id_mensaje
                )
                continue
            try:
                respuestas = Motor(db, proveedor).procesar(entrada)
                db.commit()
            except IntegrityError:  # el mismo mensaje llegó dos veces al mismo tiempo
                db.rollback()
                continue
            except Exception:
                db.rollback()
                logger.exception("Error procesando el mensaje %s", entrada.id_mensaje)
                continue

        for respuesta in respuestas:
            try:
                enviador.enviar(entrada.id_externo, respuesta)
            except ErrorWhatsApp:
                logger.exception("No se pudo enviar la respuesta a %s", entrada.id_externo)
