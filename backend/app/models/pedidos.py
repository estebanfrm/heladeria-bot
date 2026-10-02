"""Pedidos y su detalle.

Nombres y precios se copian al crear el pedido: si luego cambia el menú,
los pedidos anteriores se siguen viendo igual. Todos los montos los calcula el código.
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, enum_texto
from app.enums import EstadoPedido, TipoEntrega
from app.models.conversaciones import Cliente, Conversacion
from app.models.menu import Adicional, MedioPago, Opcion, Producto


class Pedido(Base):
    __tablename__ = "pedido"
    __table_args__ = (
        CheckConstraint("subtotal >= 0 AND domicilio >= 0", name="montos_no_negativos"),
        CheckConstraint("total = subtotal + domicilio", name="total_cuadra"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)  # número visible: PEDIDO #0042
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id"), index=True)
    conversacion_id: Mapped[int] = mapped_column(ForeignKey("conversacion.id"), index=True)
    estado: Mapped[EstadoPedido] = mapped_column(
        enum_texto(EstadoPedido), default=EstadoPedido.BORRADOR, index=True
    )
    tipo_entrega: Mapped[TipoEntrega] = mapped_column(
        enum_texto(TipoEntrega), default=TipoEntrega.DOMICILIO
    )
    subtotal: Mapped[int] = mapped_column(default=0)
    domicilio: Mapped[int] = mapped_column(default=0)  # costo del domicilio
    total: Mapped[int] = mapped_column(default=0)
    direccion: Mapped[str | None]
    medio_pago_id: Mapped[int | None] = mapped_column(ForeignKey("medio_pago.id"))
    comprobante_url: Mapped[str | None]
    creado: Mapped[datetime] = mapped_column(server_default=func.now())
    actualizado: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    cliente: Mapped[Cliente] = relationship()
    conversacion: Mapped[Conversacion] = relationship()
    medio_pago: Mapped[MedioPago | None] = relationship()
    items: Mapped[list["ItemPedido"]] = relationship(
        back_populates="pedido",
        order_by="ItemPedido.id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ItemPedido(Base):
    __tablename__ = "item_pedido"
    __table_args__ = (
        CheckConstraint("cantidad > 0", name="cantidad_positiva"),
        CheckConstraint("precio_unitario > 0", name="precio_positivo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedido.id", ondelete="CASCADE"), index=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("producto.id"))
    nombre: Mapped[str]
    cantidad: Mapped[int] = mapped_column(default=1)
    precio_unitario: Mapped[int]  # precio del producto, sin adicionales
    notas: Mapped[str | None]

    pedido: Mapped[Pedido] = relationship(back_populates="items")
    producto: Mapped[Producto] = relationship()
    opciones: Mapped[list["ItemOpcion"]] = relationship(
        back_populates="item",
        order_by="ItemOpcion.posicion",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    adicionales: Mapped[list["ItemAdicional"]] = relationship(
        back_populates="item",
        order_by="ItemAdicional.id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ItemOpcion(Base):
    """Opción elegida para un ítem. Tiene id propio y `posicion` porque una misma
    opción puede repetirse (banana split: brownie, vainilla chips, brownie)."""

    __tablename__ = "item_opcion"
    __table_args__ = (UniqueConstraint("item_id", "posicion"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("item_pedido.id", ondelete="CASCADE"))
    opcion_id: Mapped[int] = mapped_column(ForeignKey("opcion.id"))
    nombre: Mapped[str]
    posicion: Mapped[int]

    item: Mapped[ItemPedido] = relationship(back_populates="opciones")
    opcion: Mapped[Opcion] = relationship()


class ItemAdicional(Base):
    __tablename__ = "item_adicional"
    __table_args__ = (
        CheckConstraint("cantidad > 0", name="cantidad_positiva"),
        CheckConstraint("precio_unitario > 0", name="precio_positivo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("item_pedido.id", ondelete="CASCADE"), index=True
    )
    adicional_id: Mapped[int] = mapped_column(ForeignKey("adicional.id"))
    opcion_id: Mapped[int | None] = mapped_column(ForeignKey("opcion.id"))  # ej. cuál topping
    nombre: Mapped[str]
    cantidad: Mapped[int] = mapped_column(default=1)
    precio_unitario: Mapped[int]

    item: Mapped[ItemPedido] = relationship(back_populates="adicionales")
    adicional: Mapped[Adicional] = relationship()
    opcion: Mapped[Opcion | None] = relationship()
