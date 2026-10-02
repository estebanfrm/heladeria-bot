"""Canal: chat web (lo usará el widget Vue de la Fase 2; hoy se prueba desde /docs).

Adaptador delgado sobre el motor, igual que el de WhatsApp: valida la entrada,
aplica el límite del demo público y delega todo lo demás en `Motor`.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.conversacion.mensajes import Respuesta
from app.conversacion.motor import Entrada, Motor
from app.db import get_db
from app.dependencias import get_proveedor
from app.enums import Canal, OrigenMensaje
from app.ia.proveedores import ProveedorIA
from app.models import Conversacion, Mensaje

router = APIRouter(tags=["chat web"])


class MensajeChat(BaseModel):
    sesion: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9_-]{8,64}$",
        description="Id de la sesión del navegador; si no viene, se crea una nueva.",
    )
    texto: str = Field(default="", max_length=500)
    boton: str | None = Field(default=None, max_length=64, examples=["confirmar", "pago:nequi"])

    @model_validator(mode="after")
    def texto_o_boton(self):
        if not self.texto.strip() and not self.boton:
            raise ValueError("Envía un texto o un botón")
        return self


class RespuestaChat(BaseModel):
    sesion: str
    respuestas: list[Respuesta]


@router.post("/chat")
def chat(
    mensaje: MensajeChat,
    db: Annotated[Session, Depends(get_db)],
    proveedor: Annotated[ProveedorIA, Depends(get_proveedor)],
) -> RespuestaChat:
    """Envía un mensaje al bot como el chat web y devuelve sus respuestas."""
    sesion = mensaje.sesion or uuid.uuid4().hex
    limite = settings.web_chat_max_msgs_per_session
    if _mensajes_del_cliente(db, sesion) >= limite:
        # Protección de costo del demo público (sección 9): no se guarda ni se llama a la IA
        raise HTTPException(
            status_code=429,
            detail=f"Llegaste al límite de {limite} mensajes de esta demo 🍦 Gracias por probarla.",
        )
    respuestas = Motor(db, proveedor).procesar(
        Entrada(canal=Canal.WEB, id_externo=sesion, texto=mensaje.texto, boton=mensaje.boton)
    )
    db.commit()
    return RespuestaChat(sesion=sesion, respuestas=respuestas)


def _mensajes_del_cliente(db: Session, sesion: str) -> int:
    return db.scalar(
        select(func.count(Mensaje.id))
        .join(Mensaje.conversacion)
        .where(
            Conversacion.canal == Canal.WEB,
            Conversacion.id_externo == sesion,
            Mensaje.origen == OrigenMensaje.CLIENTE,
        )
    )
