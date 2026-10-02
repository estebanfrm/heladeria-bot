"""Motor de conversación: la máquina de estados de la sección 7 de PLANEACION.md.

Recibe un mensaje de cualquier canal (WhatsApp o chat web), lo interpreta (botones directo;
texto con la IA), aplica las reglas con el carrito y decide la respuesta y el siguiente estado.
La IA solo interpreta: precios, validaciones, estados y pedidos los decide este código.
"""

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.conversacion import mensajes
from app.conversacion.mensajes import Respuesta
from app.enums import (
    Canal,
    EstadoConversacion,
    EstadoPedido,
    ModoConversacion,
    OrigenMensaje,
    TipoEntrega,
)
from app.ia.interpretacion import DatosEntrega, Intencion, Interpretacion
from app.ia.proveedores import ErrorIA, ProveedorIA
from app.ia.servicio import interpretar
from app.menu.carga import leer_menu
from app.menu.schema import Menu
from app.models import Cliente, Conversacion, Mensaje, Pedido
from app.pedidos.carrito import ItemSolicitado, validar_carrito
from app.pedidos.servicio import crear_pedido

logger = logging.getLogger(__name__)

MAX_FALLOS = 2  # sin entender seguidos → pasa a una persona

E = EstadoConversacion
INACTIVOS = {E.INICIO, E.SALUDO, E.FIN, E.CANCELADA, E.PEDIDO_CONFIRMADO}


@dataclass
class Entrada:
    """Mensaje entrante, ya normalizado por el adaptador del canal."""

    canal: Canal
    id_externo: str  # teléfono en WhatsApp, id de sesión en el chat web
    texto: str = ""
    boton: str | None = None  # id de un botón (ej. "confirmar", "pago:nequi")
    media_url: str | None = None  # imagen, ej. el comprobante
    nombre: str | None = None  # nombre de perfil, si el canal lo da
    id_mensaje: str | None = None  # id del mensaje en el canal (ej. wamid de WhatsApp)


class Motor:
    def __init__(self, session: Session, proveedor: ProveedorIA):
        self.session = session
        self.proveedor = proveedor

    def procesar(self, entrada: Entrada) -> list[Respuesta]:
        conv = self._conversacion(entrada)
        self._guardar(
            conv,
            OrigenMensaje.CLIENTE,
            entrada.texto or (f"[{entrada.boton}]" if entrada.boton else None),
            entrada.media_url,
            entrada.id_mensaje,
        )
        if conv.modo is ModoConversacion.HUMANO:
            respuestas = []  # la atiende una persona (panel, Fase 3)
        else:
            respuestas = self._responder(conv, leer_menu(self.session), entrada)
        for respuesta in respuestas:
            self._guardar(conv, OrigenMensaje.BOT, respuesta.texto)
        self.session.flush()
        return respuestas

    # --- Despacho ------------------------------------------------------------------

    def _responder(self, conv: Conversacion, menu: Menu, e: Entrada) -> list[Respuesta]:
        if e.boton:
            return self._boton(conv, menu, e.boton)
        if e.media_url and conv.estado is E.ESPERANDO_PAGO:
            return self._comprobante(conv, e.media_url)
        if not e.texto.strip():
            return [mensajes.solo_texto()]

        try:
            interp = interpretar(self.proveedor, menu, e.texto, self._carrito(conv), conv.estado)
        except ErrorIA as error:
            logger.warning("La IA falló (conversación %s): %s", conv.id, error)
            return self._fallo(conv)
        if interp.intencion is Intencion.OTRO and interp.items is None and interp.entrega is None:
            return self._fallo(conv)
        conv.contexto_json["fallos"] = 0
        return self._segun_intencion(conv, menu, interp)

    def _segun_intencion(
        self, conv: Conversacion, menu: Menu, i: Interpretacion
    ) -> list[Respuesta]:
        if i.intencion is Intencion.HUMANO:
            return self._a_humano(conv)
        if i.intencion is Intencion.CANCELAR:
            return self._cancelar(conv)
        if conv.estado is E.ESPERANDO_PAGO:
            return [mensajes.esperando_comprobante(conv.contexto_json["pedido_id"])]
        if i.intencion is Intencion.VER_MENU:
            return self._carta(conv, menu)
        if i.intencion is Intencion.SALUDO and conv.estado in INACTIVOS:
            conv.estado = E.SALUDO
            return [mensajes.saludo(menu)]

        if i.entrega is not None:  # se recuerda aunque aún no sea el momento de pedirla
            conv.contexto_json["entrega"] = self._entrega(conv, i.entrega).model_dump(mode="json")
        if i.items is not None:
            return self._actualizar_carrito(conv, menu, i.items)
        if conv.estado is E.RESUMEN and (i.intencion is Intencion.CONFIRMAR or i.entrega):
            return self._confirmar(conv, menu)
        if conv.estado is E.DATOS_ENTREGA:
            return self._datos_entrega(conv, menu)
        return self._paso_actual(conv, menu)

    def _boton(self, conv: Conversacion, menu: Menu, boton: str) -> list[Respuesta]:
        if boton == "humano":
            return self._a_humano(conv)
        if conv.estado is E.ESPERANDO_PAGO:
            return [mensajes.esperando_comprobante(conv.contexto_json["pedido_id"])]
        if boton == "menu":
            return self._carta(conv, menu)
        if boton == "pedir":
            conv.estado = E.TOMANDO_PEDIDO
            return [mensajes.pedir_texto()]
        if conv.estado is E.RESUMEN:
            if boton == "confirmar":
                return self._confirmar(conv, menu)
            if boton in ("agregar", "cambiar"):
                conv.estado = E.TOMANDO_PEDIDO
                pregunta = (
                    "¿Qué más quieres agregar?" if boton == "agregar" else "¿Qué quieres cambiar?"
                )
                return [Respuesta(texto=pregunta)]
        if conv.estado is E.DATOS_ENTREGA:
            if boton.startswith("pago:"):
                datos = DatosEntrega(medio_pago=boton.removeprefix("pago:"))
            elif boton == "entrega:recoger":
                datos = DatosEntrega(tipo=TipoEntrega.RECOGER)
            else:
                return self._paso_actual(conv, menu)
            conv.contexto_json["entrega"] = self._entrega(conv, datos).model_dump(mode="json")
            return self._datos_entrega(conv, menu)
        return self._paso_actual(conv, menu)

    # --- Pasos del pedido ----------------------------------------------------------

    def _carta(self, conv: Conversacion, menu: Menu) -> list[Respuesta]:
        if conv.estado in INACTIVOS:
            conv.estado = E.TOMANDO_PEDIDO
        return [mensajes.carta(menu)]

    def _actualizar_carrito(
        self, conv: Conversacion, menu: Menu, items: list[ItemSolicitado]
    ) -> list[Respuesta]:
        conv.contexto_json["carrito"] = [i.model_dump(mode="json") for i in items]
        if not items:
            conv.estado = E.TOMANDO_PEDIDO
            return [mensajes.pedir_texto()]
        resultado = validar_carrito(menu, items)
        if resultado.completo:
            conv.estado = E.RESUMEN
            return [mensajes.resumen(resultado)]
        conv.estado = E.COMPLETANDO_OPCIONES
        return [mensajes.completar(resultado)]

    def _confirmar(self, conv: Conversacion, menu: Menu) -> list[Respuesta]:
        if not validar_carrito(menu, self._carrito(conv)).completo:
            return self._paso_actual(conv, menu)
        conv.estado = E.DATOS_ENTREGA
        return self._datos_entrega(conv, menu)

    def _datos_entrega(self, conv: Conversacion, menu: Menu) -> list[Respuesta]:
        """Pide lo que falte de entrega y pago; si ya está todo, registra el pedido."""
        entrega = DatosEntrega.model_validate(conv.contexto_json.get("entrega", {}))
        medios = {m.id: m for m in menu.medios_pago}
        aviso = None
        if entrega.medio_pago and entrega.medio_pago not in medios:
            nombres = ", ".join(m.nombre for m in menu.medios_pago)
            aviso = f"⚠️ No recibimos «{entrega.medio_pago}». Puedes pagar con: {nombres}."
            entrega.medio_pago = None
            conv.contexto_json["entrega"] = entrega.model_dump(mode="json")
        falta_direccion = entrega.tipo is not TipoEntrega.RECOGER and not entrega.direccion
        if aviso or falta_direccion or entrega.medio_pago is None:
            return [mensajes.pedir_entrega(menu, entrega, aviso)]

        tipo = entrega.tipo or TipoEntrega.DOMICILIO
        resultado = validar_carrito(menu, self._carrito(conv), tipo)
        if not resultado.completo:  # ej. algo se agotó mientras tanto
            conv.estado = E.COMPLETANDO_OPCIONES
            return [mensajes.completar(resultado)]

        medio = medios[entrega.medio_pago]
        estado = (
            EstadoPedido.PENDIENTE_PAGO
            if medio.requiere_comprobante
            else EstadoPedido.EN_PREPARACION
        )
        pedido = crear_pedido(
            self.session, conv, resultado, tipo, entrega.direccion, medio.id, estado
        )
        if entrega.direccion:
            conv.cliente.ultima_direccion = entrega.direccion
        conv.contexto_json.update(carrito=[], entrega={}, pedido_id=pedido.id)

        if medio.requiere_comprobante:
            conv.estado = E.ESPERANDO_PAGO
            return [mensajes.pagar_transferencia(pedido.id, medio, pedido.total)]
        conv.estado = E.PEDIDO_CONFIRMADO
        return [mensajes.pagar_al_recibir(pedido.id, medio, pedido.total, tipo)]

    def _comprobante(self, conv: Conversacion, media_url: str) -> list[Respuesta]:
        pedido = self.session.get(Pedido, conv.contexto_json["pedido_id"])
        pedido.comprobante_url = media_url  # el personal lo verifica (Fase 2)
        conv.estado = E.PEDIDO_CONFIRMADO
        return [mensajes.comprobante_recibido()]

    def _cancelar(self, conv: Conversacion) -> list[Respuesta]:
        if conv.estado is E.PEDIDO_CONFIRMADO:
            return self._a_humano(conv)  # ya mandó comprobante o se está preparando
        if conv.estado is E.ESPERANDO_PAGO:
            pedido = self.session.get(Pedido, conv.contexto_json["pedido_id"])
            pedido.estado = EstadoPedido.CANCELADO
        conv.contexto_json.update(carrito=[], entrega={})
        conv.estado = E.FIN
        return [mensajes.cancelado()]

    def _paso_actual(self, conv: Conversacion, menu: Menu) -> list[Respuesta]:
        """Repite lo que el bot espera en el estado actual."""
        carrito = self._carrito(conv)
        match conv.estado:
            case E.TOMANDO_PEDIDO:
                return [mensajes.pedir_texto()]
            case E.COMPLETANDO_OPCIONES | E.RESUMEN:
                return self._actualizar_carrito(conv, menu, carrito)
            case E.DATOS_ENTREGA:
                return self._datos_entrega(conv, menu)
            case E.ESPERANDO_PAGO:
                return [mensajes.esperando_comprobante(conv.contexto_json["pedido_id"])]
            case E.PEDIDO_CONFIRMADO:
                pedido = self.session.get(Pedido, conv.contexto_json["pedido_id"])
                return [mensajes.estado_pedido(pedido.id, pedido.estado)]
            case _:
                conv.estado = E.SALUDO
                return [mensajes.saludo(menu)]

    # --- Fallos y paso a humano -----------------------------------------------------

    def _fallo(self, conv: Conversacion) -> list[Respuesta]:
        fallos = conv.contexto_json.get("fallos", 0) + 1
        conv.contexto_json["fallos"] = fallos
        if fallos >= MAX_FALLOS:
            return self._a_humano(conv, por_fallos=True)
        return [mensajes.no_entendi()]

    def _a_humano(self, conv: Conversacion, por_fallos: bool = False) -> list[Respuesta]:
        conv.modo = ModoConversacion.HUMANO
        conv.contexto_json["fallos"] = 0
        return [mensajes.a_humano(por_fallos)]

    # --- Persistencia ---------------------------------------------------------------

    def _conversacion(self, e: Entrada) -> Conversacion:
        conv = self.session.scalar(
            select(Conversacion).where(
                Conversacion.canal == e.canal, Conversacion.id_externo == e.id_externo
            )
        )
        if conv is not None:
            return conv
        cliente = None
        if e.canal is Canal.WHATSAPP:
            cliente = self.session.scalar(select(Cliente).where(Cliente.telefono == e.id_externo))
        cliente = cliente or Cliente(
            telefono=e.id_externo if e.canal is Canal.WHATSAPP else None, nombre=e.nombre
        )
        conv = Conversacion(
            cliente=cliente, canal=e.canal, id_externo=e.id_externo, contexto_json={}
        )
        self.session.add(conv)
        self.session.flush()
        return conv

    def _guardar(
        self,
        conv: Conversacion,
        origen: OrigenMensaje,
        texto: str | None,
        media: str | None = None,
        id_externo: str | None = None,
    ) -> None:
        self.session.add(
            Mensaje(
                conversacion=conv,
                origen=origen,
                texto=texto,
                media_url=media,
                id_externo=id_externo,
            )
        )

    @staticmethod
    def _carrito(conv: Conversacion) -> list[ItemSolicitado]:
        return [ItemSolicitado.model_validate(i) for i in conv.contexto_json.get("carrito", [])]

    @staticmethod
    def _entrega(conv: Conversacion, nuevos: DatosEntrega) -> DatosEntrega:
        """Combina lo que ya se sabía de la entrega con lo nuevo."""
        actual = DatosEntrega.model_validate(conv.contexto_json.get("entrega", {}))
        cambios = nuevos.model_dump(exclude_none=True)
        if nuevos.direccion and not nuevos.tipo:
            cambios["tipo"] = TipoEntrega.DOMICILIO
        return actual.model_copy(update=cambios)
