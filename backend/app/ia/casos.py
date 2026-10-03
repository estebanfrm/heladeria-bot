"""Casos de evaluación de la IA, basados en el chat real del 28/09/2026.

Cada caso trae su verificación (qué debe entender la IA) y la respuesta ideal, que los tests
pasan por el ProveedorFalso para comprobar el flujo completo sin red.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from app.enums import EstadoConversacion
from app.ia.interpretacion import DatosEntrega, Intencion, Interpretacion
from app.menu.schema import Menu
from app.pedidos.carrito import AdicionalSolicitado, ItemSolicitado, validar_carrito

Verificacion = Callable[[Interpretacion, Menu], str | None]  # None = bien; texto = qué falló


@dataclass
class Caso:
    nombre: str
    mensaje: str
    ideal: Interpretacion
    verificar: Verificacion
    carrito: list[ItemSolicitado] = field(default_factory=list)
    estado: EstadoConversacion = EstadoConversacion.TOMANDO_PEDIDO


PEDIDO_INICIAL = [
    ItemSolicitado(producto="copa_queso", opciones={"sabor": ["brownie", "fresa"]}),
    ItemSolicitado(producto="banana_split"),
]
PEDIDO_COMPLETO = [
    ItemSolicitado(
        producto="copa_queso",
        opciones={"sabor": ["brownie", "fresa"], "salsa": ["frutos_rojos"], "topping": ["mani"]},
    ),
    ItemSolicitado(
        producto="banana_split",
        opciones={
            "sabor": ["brownie", "vainilla_chips", "brownie"],
            "salsa": ["frutos_rojos"],
            "topping": ["oreo"],
        },
    ),
]


def _intencion(esperada: Intencion) -> Verificacion:
    def verificar(r: Interpretacion, _menu: Menu) -> str | None:
        if r.intencion is not esperada:
            return f"intención '{r.intencion}', se esperaba '{esperada}'"
        return None

    return verificar


def _carrito_completo(total: int) -> Verificacion:
    """Lo que devolvió la IA, validado por el carrito, debe quedar completo y costar `total`."""

    def verificar(r: Interpretacion, menu: Menu) -> str | None:
        if not r.items:
            return "no devolvió items"
        resultado = validar_carrito(menu, r.items)
        if not resultado.completo:
            detalle = [p.mensaje for i in resultado.items for p in i.problemas] or [
                f"{i.nombre}: falta {f.nombre.lower()}"
                for i in resultado.items
                for f in i.faltantes
            ]
            return "carrito incompleto: " + "; ".join(detalle)
        if resultado.total != total:
            return f"total ${resultado.total}, se esperaba ${total}"
        return None

    return verificar


def _verificar_pedido_inicial(r: Interpretacion, _menu: Menu) -> str | None:
    if not r.items:
        return "no devolvió items"
    productos = [i.producto for i in r.items]
    if productos != ["copa_queso", "banana_split"]:
        return f"productos {productos}"
    copa, banana = r.items
    if copa.opciones != {"sabor": ["brownie", "fresa"]}:
        return f"opciones de la copa {copa.opciones} (no debe inventar salsa ni topping)"
    if any(banana.opciones.values()):
        return f"inventó opciones para el banana split: {banana.opciones}"
    return None


def _verificar_completar(r: Interpretacion, menu: Menu) -> str | None:
    if fallo := _carrito_completo(24000)(r, menu):
        return fallo
    banana = next(i for i in r.items if i.producto == "banana_split")
    if banana.opciones.get("sabor") != ["brownie", "vainilla_chips", "brownie"]:
        return f"sabores del banana split {banana.opciones.get('sabor')} (orden y repetición)"
    return None


def _verificar_adicional(r: Interpretacion, menu: Menu) -> str | None:
    if fallo := _carrito_completo(24000 + 1700)(r, menu):
        return fallo
    copa = next(i for i in r.items if i.producto == "copa_queso")
    if [(a.adicional, a.opcion) for a in copa.adicionales] != [("topping_extra", "oreo")]:
        return f"adicionales de la copa {copa.adicionales}"
    return None


def _verificar_conos(r: Interpretacion, menu: Menu) -> str | None:
    if fallo := _carrito_completo(3500 * 2)(r, menu):
        return fallo
    sabores = sorted(s for i in r.items for s in i.opciones.get("sabor", []) * i.cantidad)
    return None if sabores == ["fresa", "lulo"] else f"sabores {sabores}"


def _verificar_entrega(r: Interpretacion, _menu: Menu) -> str | None:
    if r.entrega is None:
        return "no devolvió datos de entrega"
    if r.entrega.medio_pago != "nequi":
        return f"medio de pago '{r.entrega.medio_pago}'"
    if "calle falsa" not in (r.entrega.direccion or "").lower():
        return f"dirección '{r.entrega.direccion}'"
    if r.items not in (None, PEDIDO_COMPLETO):
        return "modificó el carrito sin que el cliente lo pidiera"
    return None


CASOS = [
    Caso(
        nombre="saludo",
        mensaje="Hola buenas noches",
        ideal=Interpretacion(intencion=Intencion.SALUDO),
        verificar=_intencion(Intencion.SALUDO),
    ),
    Caso(
        nombre="pedido_inicial",
        mensaje="Una copa queso, con brownie… y fresa. Y un banana split",
        ideal=Interpretacion(intencion=Intencion.PEDIDO, items=PEDIDO_INICIAL),
        verificar=_verificar_pedido_inicial,
    ),
    Caso(
        nombre="completar_opciones",
        mensaje=(
            "copa: frutos rojos y maní. "
            "banana: brownie, vainilla chips, brownie, frutos rojos, oreo"
        ),
        carrito=PEDIDO_INICIAL,
        estado=EstadoConversacion.COMPLETANDO_OPCIONES,
        ideal=Interpretacion(intencion=Intencion.PEDIDO, items=PEDIDO_COMPLETO),
        verificar=_verificar_completar,
    ),
    Caso(
        nombre="agregar_adicional",
        mensaje="Y a la copa ponle un topping extra de oreo",
        carrito=PEDIDO_COMPLETO,
        estado=EstadoConversacion.RESUMEN,
        ideal=Interpretacion(
            intencion=Intencion.PEDIDO,
            items=[
                PEDIDO_COMPLETO[0].model_copy(
                    update={
                        "adicionales": [
                            AdicionalSolicitado(adicional="topping_extra", opcion="oreo")
                        ]
                    }
                ),
                PEDIDO_COMPLETO[1],
            ],
        ),
        verificar=_verificar_adicional,
    ),
    Caso(
        nombre="dos_conos_distintos",
        mensaje="dos conos de una bola, uno de fresa y otro de lulo",
        ideal=Interpretacion(
            intencion=Intencion.PEDIDO,
            items=[
                ItemSolicitado(producto="cono_1", opciones={"sabor": ["fresa"]}),
                ItemSolicitado(producto="cono_1", opciones={"sabor": ["lulo"]}),
            ],
        ),
        verificar=_verificar_conos,
    ),
    Caso(
        nombre="confirmar",
        mensaje="sí, así está bien",
        carrito=PEDIDO_COMPLETO,
        estado=EstadoConversacion.RESUMEN,
        ideal=Interpretacion(intencion=Intencion.CONFIRMAR),
        verificar=_intencion(Intencion.CONFIRMAR),
    ),
    Caso(
        nombre="entrega_y_pago",
        mensaje="Por Nequi, me mandas el número. Calle Falsa #12-34",
        carrito=PEDIDO_COMPLETO,
        estado=EstadoConversacion.DATOS_ENTREGA,
        ideal=Interpretacion(
            intencion=Intencion.ENTREGA,
            entrega=DatosEntrega(direccion="Calle Falsa #12-34", medio_pago="nequi"),
        ),
        verificar=_verificar_entrega,
    ),
    Caso(
        nombre="pide_humano",
        mensaje="mejor páseme con una persona por favor",
        ideal=Interpretacion(intencion=Intencion.HUMANO),
        verificar=_intencion(Intencion.HUMANO),
    ),
]
