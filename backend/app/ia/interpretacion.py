"""Lo que la IA devuelve al interpretar un mensaje: una intención y códigos del menú.

No hay precios ni totales: eso lo calcula el carrito. Todo se valida con Pydantic antes de usarse.
"""

from enum import StrEnum

from pydantic import BaseModel

from app.enums import TipoEntrega
from app.pedidos.carrito import ItemSolicitado


class Intencion(StrEnum):
    SALUDO = "saludo"
    VER_MENU = "ver_menu"
    PEDIDO = "pedido"  # agrega, cambia o completa productos
    CONFIRMAR = "confirmar"  # acepta el resumen del pedido
    ENTREGA = "entrega"  # da dirección, dice que recoge o elige medio de pago
    HUMANO = "humano"  # pide hablar con una persona
    CANCELAR = "cancelar"
    OTRO = "otro"  # no relacionado o no se entendió


class DatosEntrega(BaseModel):
    tipo: TipoEntrega | None = None
    direccion: str | None = None
    medio_pago: str | None = None  # código del menú, ej. "nequi"


class Interpretacion(BaseModel):
    intencion: Intencion
    # Carrito COMPLETO ya actualizado si el mensaje cambia el pedido; None si no lo toca
    items: list[ItemSolicitado] | None = None
    entrega: DatosEntrega | None = None
