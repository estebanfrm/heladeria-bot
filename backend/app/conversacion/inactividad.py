"""Cierre persistente por inactividad, compartido por el motor y el temporizador."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.conversacion import mensajes
from app.enums import Canal, EstadoConversacion, ModoConversacion, OrigenMensaje
from app.models import Conversacion, Mensaje

ESTADOS_CERRABLES = {
    EstadoConversacion.INICIO,
    EstadoConversacion.SALUDO,
    EstadoConversacion.TOMANDO_PEDIDO,
    EstadoConversacion.COMPLETANDO_OPCIONES,
    EstadoConversacion.RESUMEN,
    EstadoConversacion.DATOS_ENTREGA,
    EstadoConversacion.PEDIDO_CONFIRMADO,
}


def ahora_utc() -> datetime:
    return datetime.now(UTC)


def ultima_actividad(db: Session, conv: Conversacion) -> datetime:
    ultimo = db.scalar(select(func.max(Mensaje.creado)).where(Mensaje.conversacion_id == conv.id))
    return max(fecha for fecha in (ultimo, conv.actualizado, conv.creado) if fecha is not None)


def ventana_whatsapp_abierta(db: Session, conv: Conversacion, ahora: datetime) -> bool:
    ultimo = db.scalar(
        select(func.max(Mensaje.creado)).where(
            Mensaje.conversacion_id == conv.id, Mensaje.origen == OrigenMensaje.CLIENTE
        )
    )
    return ultimo is not None and ahora - ultimo < timedelta(hours=24)


def cerrar_si_inactiva(
    db: Session,
    conv: Conversacion,
    *,
    ahora: datetime | None = None,
    registrar_aviso: bool = True,
) -> bool:
    """El llamador mantiene bloqueada la fila hasta commit; nunca cancela un pedido."""
    if conv.estado not in ESTADOS_CERRABLES:
        return False
    ahora = ahora or ahora_utc()
    if ahora - ultima_actividad(db, conv) < timedelta(minutes=settings.chat_inactivity_minutes):
        return False
    pendiente = (
        registrar_aviso
        and conv.canal is Canal.WHATSAPP
        and ventana_whatsapp_abierta(db, conv, ahora)
    )
    conv.estado = EstadoConversacion.CANCELADA
    conv.modo = ModoConversacion.BOT
    # El historial y los pedidos siguen en sus tablas; el próximo chat empieza sin borrador.
    conv.contexto_json = {
        "cerrada_en": ahora.isoformat(),
        "motivo_cierre": "inactividad",
        "minutos_cierre": settings.chat_inactivity_minutes,
        "aviso_cierre_pendiente": pendiente,
    }
    conv.actualizado = ahora
    if registrar_aviso:
        db.add(
            Mensaje(
                conversacion_id=conv.id,
                origen=OrigenMensaje.BOT,
                texto=mensajes.chat_cerrado(settings.chat_inactivity_minutes).texto,
                creado=ahora,
            )
        )
    db.flush()
    return True
