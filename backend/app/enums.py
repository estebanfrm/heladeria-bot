"""Valores cerrados del dominio, compartidos por el esquema del seed y los modelos de BD."""

from enum import StrEnum


class TipoGrupo(StrEnum):
    SABOR = "sabor"
    SALSA = "salsa"
    TOPPING = "topping"
    FRUTA = "fruta"
    VARIANTE = "variante"  # ej. sabor de michelada, figura del infantil


class Canal(StrEnum):
    WHATSAPP = "whatsapp"
    WEB = "web"


class ModoConversacion(StrEnum):
    BOT = "bot"
    HUMANO = "humano"  # el bot se pausa y responde una persona desde el panel


class EstadoConversacion(StrEnum):
    """Estados del motor de conversación (sección 7 de PLANEACION.md)."""

    INICIO = "INICIO"
    SALUDO = "SALUDO"
    TOMANDO_PEDIDO = "TOMANDO_PEDIDO"
    COMPLETANDO_OPCIONES = "COMPLETANDO_OPCIONES"
    RESUMEN = "RESUMEN"
    DATOS_ENTREGA = "DATOS_ENTREGA"
    ESPERANDO_PAGO = "ESPERANDO_PAGO"
    PEDIDO_CONFIRMADO = "PEDIDO_CONFIRMADO"
    FIN = "FIN"
    CANCELADA = "CANCELADA"  # por inactividad


class OrigenMensaje(StrEnum):
    CLIENTE = "cliente"
    BOT = "bot"
    HUMANO = "humano"


class EstadoPedido(StrEnum):
    """Ciclo de vida del pedido (sección 8 de PLANEACION.md)."""

    BORRADOR = "BORRADOR"
    PENDIENTE_PAGO = "PENDIENTE_PAGO"
    PAGO_VERIFICADO = "PAGO_VERIFICADO"
    EN_PREPARACION = "EN_PREPARACION"
    ENVIADO = "ENVIADO"
    ENTREGADO = "ENTREGADO"
    CANCELADO = "CANCELADO"


class TipoEntrega(StrEnum):
    DOMICILIO = "domicilio"
    RECOGER = "recoger"
