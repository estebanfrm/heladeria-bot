"""Interpretar un mensaje del cliente: prompt → proveedor de IA → JSON validado.

La IA interpreta; el código decide. Lo que vuelve de aquí aún debe pasar por el carrito.
"""

from collections.abc import Sequence

from pydantic import ValidationError

from app.enums import EstadoConversacion
from app.ia.interpretacion import Interpretacion
from app.ia.prompt import construir_prompt
from app.ia.proveedores import ErrorIA, ProveedorIA
from app.menu.schema import Menu
from app.pedidos.carrito import ItemSolicitado


class RespuestaIAInvalida(ErrorIA):
    """El modelo respondió algo que no es el JSON esperado (el motor lo cuenta como fallo)."""


def interpretar(
    proveedor: ProveedorIA,
    menu: Menu,
    mensaje: str,
    carrito: Sequence[ItemSolicitado] = (),
    estado: EstadoConversacion = EstadoConversacion.TOMANDO_PEDIDO,
) -> Interpretacion:
    sistema, usuario = construir_prompt(menu, mensaje, list(carrito), estado)
    return leer_respuesta(proveedor.completar_json(sistema, usuario))


def leer_respuesta(texto: str) -> Interpretacion:
    """Valida el JSON del modelo. Tolera texto alrededor (ej. un bloque ```json ... ```)."""
    inicio, fin = texto.find("{"), texto.rfind("}")
    if inicio == -1 or fin < inicio:
        raise RespuestaIAInvalida("La IA no devolvió un objeto JSON")
    try:
        return Interpretacion.model_validate_json(texto[inicio : fin + 1])
    except ValidationError as e:
        primero = e.errors()[0]
        donde = ".".join(str(parte) for parte in primero["loc"]) or "raíz"
        raise RespuestaIAInvalida(
            f"JSON de la IA inválido en {donde}: {primero['msg']} ({e.error_count()} errores)"
        ) from e
