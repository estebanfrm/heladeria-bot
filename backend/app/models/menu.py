"""Catálogo del menú: se carga desde seeds/*.json y lo edita el panel.

Cada tabla tiene una PK entera y un `codigo` estable (el `id` del seed, ej. "copa_queso"),
que es lo que ve la IA. Los precios viven aquí y solo los usa el código, nunca la IA.
"""

from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, enum_texto
from app.enums import TipoGrupo


class Negocio(Base):
    """Datos generales del negocio (una sola fila)."""

    __tablename__ = "negocio"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str]
    moneda: Mapped[str] = mapped_column(default="COP")
    ciudad: Mapped[str] = mapped_column(default="")
    horario: Mapped[str] = mapped_column(default="")
    costo_domicilio: Mapped[int] = mapped_column(default=0)
    nota_domicilio: Mapped[str] = mapped_column(default="")
    # `version` del seed aplicado; el arranque solo recarga si el seed trae una mayor
    version_menu: Mapped[int] = mapped_column(default=0, server_default="0")


class Categoria(Base):
    __tablename__ = "categoria"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(unique=True)
    nombre: Mapped[str]
    orden: Mapped[int] = mapped_column(default=0)
    activo: Mapped[bool] = mapped_column(default=True, server_default=true())

    productos: Mapped[list["Producto"]] = relationship(back_populates="categoria")


class GrupoOpcion(Base):
    """Lista de opciones elegibles, ej. salsas_base = frutos rojos / maracuyá / lecherita."""

    __tablename__ = "grupo_opcion"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(unique=True)
    tipo: Mapped[TipoGrupo] = mapped_column(enum_texto(TipoGrupo))
    nombre: Mapped[str]
    activo: Mapped[bool] = mapped_column(default=True, server_default=true())

    opciones: Mapped[list["Opcion"]] = relationship(
        back_populates="grupo", order_by="Opcion.id", cascade="all, delete-orphan"
    )


class Opcion(Base):
    """Opción dentro de un grupo. El código es único por grupo, no global:
    "frutos_rojos" existe como salsa en varios grupos y como sabor de michelada."""

    __tablename__ = "opcion"
    __table_args__ = (UniqueConstraint("grupo_id", "codigo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    grupo_id: Mapped[int] = mapped_column(ForeignKey("grupo_opcion.id", ondelete="CASCADE"))
    codigo: Mapped[str]
    nombre: Mapped[str]
    disponible: Mapped[bool] = mapped_column(default=True)  # False = agotado hoy (panel)
    activo: Mapped[bool] = mapped_column(default=True, server_default=true())  # sigue en la carta

    grupo: Mapped[GrupoOpcion] = relationship(back_populates="opciones")


class Producto(Base):
    __tablename__ = "producto"
    __table_args__ = (CheckConstraint("precio > 0", name="precio_positivo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(unique=True)
    nombre: Mapped[str]
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categoria.id"), index=True)
    precio: Mapped[int]  # pesos COP, sin centavos
    descripcion: Mapped[str] = mapped_column(default="")
    activo: Mapped[bool] = mapped_column(default=True)

    categoria: Mapped[Categoria] = relationship(back_populates="productos")
    selecciones: Mapped[list["ProductoSeleccion"]] = relationship(
        back_populates="producto",
        order_by="ProductoSeleccion.orden",
        cascade="all, delete-orphan",
    )


class ProductoSeleccion(Base):
    """Qué debe elegir el cliente para un producto.

    Ej. copa queso = 2 de `sabores` + 1 de `salsas_base` + 1 de `toppings_base`.
    """

    __tablename__ = "producto_seleccion"
    __table_args__ = (CheckConstraint("cantidad > 0", name="cantidad_positiva"),)

    producto_id: Mapped[int] = mapped_column(
        ForeignKey("producto.id", ondelete="CASCADE"), primary_key=True
    )
    grupo_id: Mapped[int] = mapped_column(ForeignKey("grupo_opcion.id"), primary_key=True)
    cantidad: Mapped[int]
    permite_repetir: Mapped[bool] = mapped_column(default=True)  # brownie, vainilla chips, brownie
    orden: Mapped[int] = mapped_column(default=0)

    producto: Mapped[Producto] = relationship(back_populates="selecciones")
    grupo: Mapped[GrupoOpcion] = relationship()


class Adicional(Base):
    __tablename__ = "adicional"
    __table_args__ = (CheckConstraint("precio > 0", name="precio_positivo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(unique=True)
    nombre: Mapped[str]
    precio: Mapped[int]
    # Si no es nulo, el cliente debe elegir del grupo (ej. topping adicional → cuál topping)
    grupo_id: Mapped[int | None] = mapped_column(ForeignKey("grupo_opcion.id"))
    activo: Mapped[bool] = mapped_column(default=True)

    grupo: Mapped[GrupoOpcion | None] = relationship()


class MedioPago(Base):
    __tablename__ = "medio_pago"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(unique=True)
    nombre: Mapped[str]
    numero_cuenta: Mapped[str | None]  # en el demo siempre ficticio
    titular: Mapped[str | None]
    requiere_comprobante: Mapped[bool]  # False = efectivo / datáfono al entregar
    activo: Mapped[bool] = mapped_column(default=True)
