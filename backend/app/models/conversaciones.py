"""Clientes, conversaciones (una por cliente y canal) y su historial de mensajes."""

from datetime import datetime

from sqlalchemy import ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, enum_texto
from app.enums import Canal, EstadoConversacion, ModoConversacion, OrigenMensaje


class Cliente(Base):
    __tablename__ = "cliente"

    id: Mapped[int] = mapped_column(primary_key=True)
    telefono: Mapped[str | None] = mapped_column(unique=True)  # nulo en el chat web anónimo
    nombre: Mapped[str | None]
    ultima_direccion: Mapped[str | None]
    # Ley 1581 de 2012: cuándo autorizó el tratamiento de datos (nulo = no ha autorizado)
    acepto_datos_en: Mapped[datetime | None]
    creado: Mapped[datetime] = mapped_column(server_default=func.now())

    conversaciones: Mapped[list["Conversacion"]] = relationship(back_populates="cliente")


class Conversacion(Base):
    """Hilo de un cliente en un canal. El motor la reinicia al terminar cada pedido."""

    __tablename__ = "conversacion"
    __table_args__ = (UniqueConstraint("canal", "id_externo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id"), index=True)
    canal: Mapped[Canal] = mapped_column(enum_texto(Canal))
    id_externo: Mapped[str]  # teléfono en WhatsApp, id de sesión en el chat web
    estado: Mapped[EstadoConversacion] = mapped_column(
        enum_texto(EstadoConversacion), default=EstadoConversacion.INICIO
    )
    modo: Mapped[ModoConversacion] = mapped_column(
        enum_texto(ModoConversacion), default=ModoConversacion.BOT
    )
    # Carrito en curso, fallos de interpretación, etc. MutableDict detecta cambios in situ.
    contexto_json: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSONB), default=dict)
    creado: Mapped[datetime] = mapped_column(server_default=func.now())
    actualizado: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    cliente: Mapped[Cliente] = relationship(back_populates="conversaciones")
    mensajes: Mapped[list["Mensaje"]] = relationship(
        back_populates="conversacion",
        order_by="Mensaje.id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Mensaje(Base):
    __tablename__ = "mensaje"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversacion_id: Mapped[int] = mapped_column(
        ForeignKey("conversacion.id", ondelete="CASCADE"), index=True
    )
    origen: Mapped[OrigenMensaje] = mapped_column(enum_texto(OrigenMensaje))
    texto: Mapped[str | None]
    media_url: Mapped[str | None]  # ej. imagen del comprobante
    creado: Mapped[datetime] = mapped_column(server_default=func.now())

    conversacion: Mapped[Conversacion] = relationship(back_populates="mensajes")
