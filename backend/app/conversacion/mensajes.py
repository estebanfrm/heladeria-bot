"""Textos del bot (estilo del ejemplo de la sección 7 de PLANEACION.md).

Funciones puras: reciben datos ya calculados por el código (precios, totales, faltantes)
y solo los formatean. Los botones son genéricos; cada canal decide cómo mostrarlos.
"""

from typing import Literal

from pydantic import BaseModel

from app.enums import EstadoPedido, TipoEntrega
from app.ia.interpretacion import DatosEntrega
from app.menu.schema import MedioPago, Menu
from app.pedidos.carrito import ItemValidado, ResultadoCarrito


class Boton(BaseModel):
    id: str
    titulo: str


class Respuesta(BaseModel):
    texto: str
    botones: list[Boton] = []
    documento: Literal["menu"] | None = None


BOTONES_INICIO = [
    Boton(id="menu", titulo="Ver menú"),
    Boton(id="pedir", titulo="Hacer pedido"),
    Boton(id="humano", titulo="Hablar con alguien"),
]
BOTONES_RESUMEN = [
    Boton(id="confirmar", titulo="Confirmar"),
    Boton(id="agregar", titulo="Agregar algo"),
    Boton(id="cambiar", titulo="Cambiar"),
]

ESTADOS_PEDIDO = {
    EstadoPedido.BORRADOR: "en borrador",
    EstadoPedido.PENDIENTE_PAGO: "pendiente de pago",
    EstadoPedido.PAGO_VERIFICADO: "con el pago verificado",
    EstadoPedido.EN_PREPARACION: "en preparación 🍦",
    EstadoPedido.ENVIADO: "en camino 🛵",
    EstadoPedido.ENTREGADO: "entregado ✅",
    EstadoPedido.CANCELADO: "cancelado",
}


def pesos(valor: int) -> str:
    """24000 → '$24.000'."""
    return "$" + f"{valor:,}".replace(",", ".")


def numero_pedido(pedido_id: int) -> str:
    return f"#{pedido_id:04d}"


def saludo(menu: Menu) -> Respuesta:
    return Respuesta(
        texto=f"¡Hola! 🍦 Bienvenido a {menu.negocio.nombre}. ¿Qué se te antoja?",
        botones=BOTONES_INICIO,
    )


def chat_cerrado(minutos: int) -> Respuesta:
    return Respuesta(
        texto=f"Cerré esta conversación tras {minutos} minutos sin respuesta. "
        "Si quieres volver a pedir, pulsa «Nuevo chat» o escribe «nuevo chat». "
        "Los pedidos ya registrados se conservan.",
        botones=[Boton(id="chat:nuevo", titulo="Nuevo chat")],
    )


def pedir_texto() -> Respuesta:
    return Respuesta(
        texto="¡Dale! Escríbeme lo que quieres, por ejemplo: "
        "«una copa queso con brownie y fresa y un banana split» 😋"
    )


def carta(menu: Menu, *, pdf: bool = False) -> Respuesta:
    if pdf:
        return Respuesta(
            texto="🍦 Aquí tienes nuestro menú. Escríbeme lo que quieres pedir 😋",
            documento="menu",
        )
    lineas = [f"🍦 *Menú de {menu.negocio.nombre}*"]
    for categoria in sorted(menu.categorias, key=lambda c: c.orden):
        productos = [p for p in menu.productos if p.categoria == categoria.id]
        if productos:
            lineas.append(f"\n*{categoria.nombre}*")
            lineas += [f"• {p.nombre} — {pesos(p.precio)}" for p in productos]
    if menu.adicionales:
        lineas.append("\n*Adicionales*")
        lineas += [f"• {a.nombre} — {pesos(a.precio)}" for a in menu.adicionales]
    lineas.append("\nEscríbeme lo que quieres y te ayudo a armarlo 😋")
    return Respuesta(texto="\n".join(lineas))


def descripcion_item(item: ItemValidado) -> str:
    """'brownie, vainilla chips, brownie · frutos rojos · oreo triturado' (+ adicionales)."""
    por_grupo: dict[str, list[str]] = {}
    for opcion in item.opciones:
        por_grupo.setdefault(opcion.grupo, []).append(opcion.nombre.lower())
    partes = [", ".join(nombres) for nombres in por_grupo.values()]
    for a in item.adicionales:
        extra = a.nombre.lower() + (f" ({a.opcion.nombre.lower()})" if a.opcion else "")
        partes.append(f"+ {extra}" if a.cantidad == 1 else f"+ {a.cantidad}× {extra}")
    return " · ".join(partes)


def completar(resultado: ResultadoCarrito) -> Respuesta:
    """Problemas y todo lo que falta elegir de cada producto, en UN solo mensaje."""
    lineas = [f"⚠️ {p.mensaje}" for item in resultado.items for p in item.problemas]
    pendientes = [item for item in resultado.items if item.faltantes]
    if not pendientes:
        lineas.append("\n¿Me ayudas a corregirlo?")
        return Respuesta(texto="\n".join(lineas).strip())

    lineas.append("\nPara completar tu pedido:" if lineas else "¡Listo! Para completar tu pedido:")
    for item in pendientes:
        elegido = descripcion_item(item)
        lineas.append(f"\n*{item.nombre}*" + (f" ({elegido})" if elegido else ""))
        adicionales = {a.codigo: a.nombre for a in item.adicionales}
        for f in item.faltantes:
            etiqueta = adicionales.get(f.adicional, f.nombre) if f.adicional else f.nombre
            opciones = " / ".join(o.nombre.lower() for o in f.opciones)
            lineas.append(f"• {etiqueta} (elige {f.cantidad}): {opciones}")
    lineas.append("\nRespóndeme todo en un solo mensaje 🙌")
    return Respuesta(texto="\n".join(lineas).strip())


def resumen(resultado: ResultadoCarrito) -> Respuesta:
    lineas = ["📝 *Tu pedido:*"]
    for item in resultado.items:
        descripcion = descripcion_item(item)
        lineas.append(
            f"{item.solicitud.cantidad}× {item.nombre}"
            + (f" — {descripcion}" if descripcion else "")
            + f" — {pesos(item.total)}"
        )
    if resultado.domicilio:
        lineas.append(f"Domicilio — {pesos(resultado.domicilio)}")
    lineas.append(f"*Total: {pesos(resultado.total)}*")
    return Respuesta(texto="\n".join(lineas), botones=BOTONES_RESUMEN)


def pedir_entrega(menu: Menu, entrega: DatosEntrega, aviso: str | None = None) -> Respuesta:
    falta_direccion = entrega.tipo is not TipoEntrega.RECOGER and not entrega.direccion
    falta_pago = entrega.medio_pago is None
    if falta_direccion and falta_pago:
        texto = "¿A qué dirección lo enviamos y cómo pagas? (si prefieres, lo recoges en el local)"
    elif falta_direccion:
        texto = "¿A qué dirección lo enviamos? (o dime si lo recoges en el local)"
    else:
        texto = "¿Cómo vas a pagar?"
    if falta_direccion and menu.negocio.domicilio.costo:
        texto += f"\nEl domicilio cuesta {pesos(menu.negocio.domicilio.costo)}."

    botones = (
        [Boton(id=f"pago:{m.id}", titulo=m.nombre) for m in menu.medios_pago] if falta_pago else []
    )
    if falta_direccion:
        botones.append(Boton(id="entrega:recoger", titulo="Recoger en el local"))
    return Respuesta(texto=f"{aviso}\n{texto}" if aviso else texto, botones=botones)


def confirmar_direccion(direccion: str) -> Respuesta:
    return Respuesta(
        texto=f"Recibí esta dirección: {direccion}\n¿La confirmas para el domicilio?",
        botones=[
            Boton(id="direccion:confirmar", titulo="Sí, esa dirección"),
            Boton(id="direccion:corregir", titulo="Corregir dirección"),
        ],
    )


def aclarar_direccion() -> Respuesta:
    return Respuesta(
        texto="Necesito la dirección completa para el domicilio: vía, número y placa. "
        "Por ejemplo: «Cra 40 #96A-02». Puedes añadir apartamento y barrio.",
        botones=[Boton(id="entrega:recoger", titulo="Recoger en el local")],
    )


def pagar_transferencia(pedido_id: int, medio: MedioPago, total: int) -> Respuesta:
    return Respuesta(
        texto=(
            f"Pedido *{numero_pedido(pedido_id)}* registrado ✅\n"
            f"Envía *{pesos(total)}* al *{medio.nombre} {medio.cuenta}* a nombre de "
            f"*{medio.titular}* y mándame el comprobante 📸"
        ),
        botones=[Boton(id="cambiar", titulo="Cambiar pedido")],
    )


def pagar_al_recibir(pedido_id: int, medio: MedioPago, total: int, tipo: TipoEntrega) -> Respuesta:
    cuando = "al recogerlo" if tipo is TipoEntrega.RECOGER else "al recibirlo"
    return Respuesta(
        texto=(
            f"¡Listo! Tu pedido *{numero_pedido(pedido_id)}* ya está en preparación 🍦\n"
            f"Total a pagar {cuando}: *{pesos(total)}* — {medio.nombre}"
        ),
        botones=[Boton(id="cambiar", titulo="Cambiar pedido")],
    )


def comprobante_recibido() -> Respuesta:
    return Respuesta(
        texto="¡Recibido! En cuanto confirmemos el pago empezamos a preparar tu pedido ✅"
    )


def esperando_comprobante(pedido_id: int) -> Respuesta:
    return Respuesta(
        texto=(
            f"Estoy esperando la foto del comprobante del pedido *{numero_pedido(pedido_id)}* 📸\n"
            "Si necesitas ayuda, escribe «asesor»."
        ),
        botones=[Boton(id="cambiar", titulo="Cambiar pedido")],
    )


def estado_pedido(pedido_id: int, estado: EstadoPedido) -> Respuesta:
    return Respuesta(
        texto=f"Tu pedido *{numero_pedido(pedido_id)}* está {ESTADOS_PEDIDO[estado]}.\n"
        "Si quieres pedir algo más, escríbeme 😋"
    )


def solo_texto() -> Respuesta:
    return Respuesta(texto="Por ahora solo puedo leer mensajes de texto 🙂 ¿Qué se te antoja?")


def no_entendi() -> Respuesta:
    return Respuesta(
        texto="No te entendí 🤔 ¿Me lo repites? Por ejemplo: «una copa queso con brownie y fresa»."
    )


def a_humano(por_fallos: bool = False) -> Respuesta:
    inicio = "Parece que no te estoy entendiendo 😅 " if por_fallos else ""
    return Respuesta(
        texto=f"{inicio}El chat queda pendiente de atención de una persona del equipo 🙋. "
        "Las respuestas automáticas están pausadas. Escribe «bot» para retomarlas."
    )


def cancelado() -> Respuesta:
    return Respuesta(texto="Listo, cancelé tu pedido. Cuando se te antoje algo, aquí estoy 🍦")


def condiciones_comerciales() -> Respuesta:
    return Respuesta(
        texto="Los precios y adicionales son los del menú. No puedo aplicar descuentos, "
        "cupones ni promociones que no estén autorizados, ni cambiar un pago por un mensaje. "
        "Tu pedido conserva sus valores. Si quieres modificar productos, escribe «cambiar pedido»."
    )


def edicion_bloqueada() -> Respuesta:
    return Respuesta(
        texto="Ese pedido ya tiene comprobante, pago registrado o despacho, y no puedo "
        "cambiarlo automáticamente. Para revisarlo, pulsa «Hablar con alguien».",
        botones=[Boton(id="humano", titulo="Hablar con alguien")],
    )


def pedir_cambio(pedido_id: int) -> Respuesta:
    return Respuesta(
        texto=f"¿Qué quieres cambiar del pedido {numero_pedido(pedido_id)}? "
        "Escríbeme los productos, cantidades o sabores. Guardaré los cambios cuando confirmes "
        "el nuevo resumen; antes de pagar usa el total actualizado.",
        botones=[Boton(id="edicion:descartar", titulo="Mantener pedido")],
    )
