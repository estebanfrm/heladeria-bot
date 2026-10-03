"""Motor de conversación: la máquina de estados de la sección 7 de PLANEACION.md.

Recibe un mensaje de cualquier canal (WhatsApp o chat web), lo interpreta (botones directo;
texto con la IA), aplica las reglas con el carrito y decide la respuesta y el siguiente estado.
La IA solo interpreta: precios, validaciones, estados y pedidos los decide este código.
"""

import logging
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.conversacion import mensajes
from app.conversacion.inactividad import ahora_utc, cerrar_si_inactiva
from app.conversacion.mensajes import Respuesta
from app.conversacion.protecciones import (
    CAMBIO,
    cantidad_invalida,
    normalizar,
    restriccion_comercial,
)
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
from app.pedidos.servicio import crear_pedido, editable, recuperar_carrito

logger = logging.getLogger(__name__)

MAX_FALLOS = 2  # sin entender seguidos → pasa a una persona

E = EstadoConversacion
INACTIVOS = {E.INICIO, E.SALUDO, E.FIN, E.CANCELADA, E.PEDIDO_CONFIRMADO}

# Direcciones inequívocas cuando se está pidiendo la entrega. No dependen de la IA.
CALLE = (
    r"(?:carrera|cra\.?|cr\.?|kr\.?|kra\.?|calle|cl\.?|cll\.?|avenida|av\.?|"
    r"diagonal|diag\.?|dg\.?|transversal|transv\.?|tv\.?)\s*\d+[a-z]?"
    r"(?:\s+bis)?(?:\s+(?:norte|sur|este|oeste))?"
)
COMPLEMENTO = (
    r"(?:[ ,]+(?:apto\.?|apartamento|casa|barrio|torre|piso|interior|bloque)"
    r"\s+[\w .,-]+)*"
)
DIRECCION = re.compile(
    rf"{CALLE}(?:\s*(?:#|no\.?|número)\s*|\s+)"
    rf"\d+[a-z]?(?:\s*[-–]\s*|\s+)\d+[a-z]?{COMPLEMENTO}",
    re.IGNORECASE,
)
# Sin separador entre calle transversal y placa, se pide confirmar sin inventar números.
DIRECCION_COMPACTA = re.compile(
    rf"{CALLE}(?:\s*(?:#|no\.?|número)\s*|\s+)\d+[a-z]\d+{COMPLEMENTO}",
    re.IGNORECASE,
)
INICIO_DIRECCION = re.compile(
    rf"{CALLE}(?=\s|#|$)",
    re.IGNORECASE,
)


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
        cerrar_si_inactiva(self.session, conv, registrar_aviso=False)
        self._guardar(
            conv,
            OrigenMensaje.CLIENTE,
            entrada.texto or (f"[{entrada.boton}]" if entrada.boton else None),
            entrada.media_url,
            entrada.id_mensaje,
        )
        if conv.estado is E.CANCELADA:
            if entrada.boton == "chat:nuevo" or entrada.texto.strip().lower() in {
                "nuevo chat",
                "nuevo pedido",
                "iniciar chat",
                "empezar de nuevo",
            }:
                conv.contexto_json = {"sesion_iniciada_en": ahora_utc().isoformat()}
                conv.estado = E.SALUDO
                conv.modo = ModoConversacion.BOT
                respuestas = [mensajes.saludo(leer_menu(self.session))]
            else:
                conv.contexto_json["aviso_cierre_pendiente"] = False
                respuestas = [
                    mensajes.chat_cerrado(
                        conv.contexto_json.get("minutos_cierre", settings.chat_inactivity_minutes)
                    )
                ]
        elif conv.modo is ModoConversacion.HUMANO and entrada.texto.strip().lower() in {
            "bot",
            "volver al bot",
        }:
            conv.modo = ModoConversacion.BOT
            conv.contexto_json["fallos"] = 0
            respuestas = self._paso_actual(conv, leer_menu(self.session))
        elif conv.modo is ModoConversacion.HUMANO:
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
        if e.media_url and (
            conv.estado is E.ESPERANDO_PAGO or conv.contexto_json.get("edicion_pedido_id")
        ):
            return self._comprobante(conv, e.media_url)
        if not e.texto.strip():
            return [mensajes.solo_texto()]
        if len(e.texto) > settings.bot_max_text_chars:
            return [
                Respuesta(
                    texto=f"Escribe tu mensaje en máximo {settings.bot_max_text_chars} caracteres."
                )
            ]
        if restriccion_comercial(e.texto):
            return [mensajes.condiciones_comerciales()]
        if cantidad_invalida(e.texto):
            return [
                Respuesta(
                    texto="La cantidad debe ser un número entero mayor que cero. "
                    "Para quitar un producto, escribe «quitar» y su nombre."
                )
            ]

        texto = normalizar(e.texto)
        if texto in {"mantener pedido", "cancelar cambio", "dejar el pedido igual"}:
            return self._descartar_edicion(conv, menu)
        if conv.estado is E.PEDIDO_CONFIRMADO and (
            texto in {"nuevo pedido", "otro pedido"} or texto.startswith("ahora ")
        ):
            conv.contexto_json = {"carrito": [], "entrega": {}}
            conv.estado = E.TOMANDO_PEDIDO
            if texto in {"nuevo pedido", "otro pedido"}:
                return [mensajes.pedir_texto()]
        if texto in {"cambiar", "cambiar pedido", "quiero cambiar mi pedido", "camviar pedido"}:
            return self._iniciar_edicion(conv, menu)
        if conv.estado in {E.ESPERANDO_PAGO, E.PEDIDO_CONFIRMADO} and CAMBIO.search(texto):
            r = self._iniciar_edicion(conv, menu)
            if conv.estado is not E.TOMANDO_PEDIDO:
                return r

        if e.texto.strip().lower() in {"menu", "menú", "ver menu", "ver menú"}:
            return self._carta(conv, menu)
        if conv.estado is E.DATOS_ENTREGA:
            direccion = e.texto.strip()
            if conv.contexto_json.get("direccion_por_confirmar") and direccion.lower() in {
                "sí",
                "si",
                "confirmar",
                "sí, esa dirección",
            }:
                return self._boton(conv, menu, "direccion:confirmar")
            if DIRECCION.fullmatch(direccion):
                conv.contexto_json["fallos"] = 0
                conv.contexto_json.pop("direccion_por_confirmar", None)
                conv.contexto_json["entrega"] = self._entrega(
                    conv, DatosEntrega(direccion=direccion)
                ).model_dump(mode="json")
                return self._datos_entrega(conv, menu)
            if DIRECCION_COMPACTA.fullmatch(direccion):
                conv.contexto_json["fallos"] = 0
                conv.contexto_json["direccion_por_confirmar"] = direccion
                return [mensajes.confirmar_direccion(direccion)]
            if re.fullmatch(CALLE, direccion, re.IGNORECASE):
                conv.contexto_json["fallos"] = 0
                conv.contexto_json.pop("direccion_por_confirmar", None)
                return [
                    Respuesta(
                        texto="Me falta el número de la dirección. "
                        "Escríbela completa, por ejemplo: «Cra 8 #80-70»."
                    )
                ]
            if INICIO_DIRECCION.match(direccion):
                conv.contexto_json["fallos"] = 0
                conv.contexto_json.pop("direccion_por_confirmar", None)
                return [mensajes.aclarar_direccion()]

        try:
            carrito = self._carrito(conv)
            if conv.estado in {E.ESPERANDO_PAGO, E.PEDIDO_CONFIRMADO}:
                pedido = self._pedido_vigente(conv)
                if pedido is not None:
                    carrito = recuperar_carrito(pedido)
            interp = interpretar(self.proveedor, menu, e.texto, carrito, conv.estado)
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
        if i.intencion is Intencion.CAMBIAR or (
            i.items is not None and conv.estado in {E.ESPERANDO_PAGO, E.PEDIDO_CONFIRMADO}
        ):
            r = self._iniciar_edicion(conv, menu)
            if conv.estado is not E.TOMANDO_PEDIDO or (i.items is None and i.entrega is None):
                return r
        if conv.estado is E.ESPERANDO_PAGO:
            return [mensajes.esperando_comprobante(conv.contexto_json["pedido_id"])]
        if i.intencion is Intencion.VER_MENU:
            return self._carta(conv, menu)
        if i.intencion is Intencion.SALUDO and conv.estado in INACTIVOS:
            conv.estado = E.SALUDO
            return [mensajes.saludo(menu)]

        if i.entrega is not None:  # se recuerda aunque aún no sea el momento de pedirla
            conv.contexto_json["entrega"] = self._entrega(conv, i.entrega).model_dump(mode="json")
            if conv.contexto_json.get("edicion_pedido_id") and i.items is None:
                return self._actualizar_carrito(conv, menu, self._carrito(conv))
        if i.items is not None:
            return self._actualizar_carrito(conv, menu, i.items)
        if conv.estado is E.RESUMEN and (i.intencion is Intencion.CONFIRMAR or i.entrega):
            return self._confirmar(conv, menu)
        if conv.estado is E.DATOS_ENTREGA:
            return self._datos_entrega(conv, menu)
        return self._paso_actual(conv, menu)

    def _boton(self, conv: Conversacion, menu: Menu, boton: str) -> list[Respuesta]:
        if boton == "chat:nuevo":
            return self._paso_actual(
                conv, menu
            )  # botón de un cierre anterior: no vacía otro pedido
        if boton == "humano":
            return self._a_humano(conv)
        if boton == "cambiar":
            return self._iniciar_edicion(conv, menu)
        if boton == "agregar" and conv.estado is E.PEDIDO_CONFIRMADO:
            return self._iniciar_edicion(conv, menu)
        if boton == "edicion:descartar":
            return self._descartar_edicion(conv, menu)
        if conv.estado is E.ESPERANDO_PAGO:
            return [mensajes.esperando_comprobante(conv.contexto_json["pedido_id"])]
        if boton == "menu":
            return self._carta(conv, menu)
        if boton == "pedir":
            if conv.estado is E.PEDIDO_CONFIRMADO:
                conv.contexto_json = {"carrito": [], "entrega": {}}
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
            if boton == "direccion:confirmar":
                direccion = conv.contexto_json.pop("direccion_por_confirmar", None)
                if not direccion:
                    return self._paso_actual(conv, menu)
                datos = DatosEntrega(direccion=direccion)
            elif boton == "direccion:corregir":
                conv.contexto_json.pop("direccion_por_confirmar", None)
                return [mensajes.aclarar_direccion()]
            elif boton.startswith("pago:"):
                datos = DatosEntrega(medio_pago=boton.removeprefix("pago:"))
            elif boton == "entrega:recoger":
                conv.contexto_json.pop("direccion_por_confirmar", None)
                datos = DatosEntrega(tipo=TipoEntrega.RECOGER)
            else:
                return self._paso_actual(conv, menu)
            conv.contexto_json["entrega"] = self._entrega(conv, datos).model_dump(mode="json")
            return self._datos_entrega(conv, menu)
        return self._paso_actual(conv, menu)

    # --- Pasos del pedido ----------------------------------------------------------

    def _pedido_vigente(self, conv: Conversacion) -> Pedido | None:
        id_pedido = conv.contexto_json.get("edicion_pedido_id") or conv.contexto_json.get(
            "pedido_id"
        )
        if not id_pedido:
            return None
        return self.session.scalar(
            select(Pedido)
            .where(
                Pedido.id == id_pedido,
                Pedido.cliente_id == conv.cliente_id,
                Pedido.conversacion_id == conv.id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    def _iniciar_edicion(self, conv: Conversacion, menu: Menu) -> list[Respuesta]:
        pedido = self._pedido_vigente(conv)
        if pedido is None and (
            conv.contexto_json.get("pedido_id") or conv.contexto_json.get("edicion_pedido_id")
        ):
            return [mensajes.edicion_bloqueada()]
        if pedido is not None:
            if not editable(pedido):
                return [mensajes.edicion_bloqueada()]
            if not conv.contexto_json.get("edicion_pedido_id"):
                conv.contexto_json["carrito"] = [
                    i.model_dump(mode="json") for i in recuperar_carrito(pedido)
                ]
                conv.contexto_json["entrega"] = DatosEntrega(
                    tipo=pedido.tipo_entrega,
                    direccion=pedido.direccion,
                    medio_pago=pedido.medio_pago.codigo,
                ).model_dump(mode="json")
            conv.contexto_json["edicion_pedido_id"] = pedido.id
            conv.estado = E.TOMANDO_PEDIDO
            return [mensajes.pedir_cambio(pedido.id)]
        conv.estado = E.TOMANDO_PEDIDO
        return [Respuesta(texto="¿Qué quieres cambiar? Escríbeme el pedido como lo quieres ahora.")]

    def _descartar_edicion(self, conv: Conversacion, menu: Menu) -> list[Respuesta]:
        if not conv.contexto_json.get("edicion_pedido_id"):
            return self._paso_actual(conv, menu)
        pedido = self._pedido_vigente(conv)
        conv.contexto_json.pop("edicion_pedido_id", None)
        conv.contexto_json.update(carrito=[], entrega={})
        conv.estado = (
            E.ESPERANDO_PAGO
            if pedido
            and pedido.estado is EstadoPedido.PENDIENTE_PAGO
            and not pedido.comprobante_url
            else E.PEDIDO_CONFIRMADO
        )
        return [Respuesta(texto="Conservé tu pedido anterior; no se guardaron los cambios.")]

    def _carta(self, conv: Conversacion, menu: Menu) -> list[Respuesta]:
        if conv.estado in INACTIVOS - {E.PEDIDO_CONFIRMADO}:
            conv.estado = E.TOMANDO_PEDIDO
        return [
            mensajes.carta(
                menu, pdf=conv.canal is Canal.WHATSAPP and settings.wa_menu_pdf_file is not None
            )
        ]

    def _actualizar_carrito(
        self, conv: Conversacion, menu: Menu, items: list[ItemSolicitado]
    ) -> list[Respuesta]:
        conv.contexto_json.pop("direccion_por_confirmar", None)
        conv.contexto_json["carrito"] = [i.model_dump(mode="json") for i in items]
        if not items:
            conv.estado = E.TOMANDO_PEDIDO
            return [mensajes.pedir_texto()]
        resultado = validar_carrito(menu, items)
        if resultado.completo:
            conv.estado = E.RESUMEN
            r = mensajes.resumen(resultado)
            if conv.contexto_json.get("edicion_pedido_id"):
                r.texto = "Revisa los cambios antes de guardarlos.\n" + r.texto
                r.botones.append(mensajes.Boton(id="edicion:descartar", titulo="Mantener pedido"))
            return [r]
        conv.estado = E.COMPLETANDO_OPCIONES
        return [mensajes.completar(resultado)]

    def _confirmar(self, conv: Conversacion, menu: Menu) -> list[Respuesta]:
        if conv.contexto_json.get("edicion_pedido_id"):
            pedido = self._pedido_vigente(conv)
            if pedido is None or not editable(pedido):
                return [mensajes.edicion_bloqueada()]
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
        if falta_direccion and conv.contexto_json.get("direccion_por_confirmar"):
            return [mensajes.confirmar_direccion(conv.contexto_json["direccion_por_confirmar"])]
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
        anterior = None
        if conv.contexto_json.get("edicion_pedido_id"):
            anterior = self._pedido_vigente(conv)
            if anterior is None or not editable(anterior):
                return [mensajes.edicion_bloqueada()]
        pedido = crear_pedido(
            self.session,
            conv,
            resultado,
            tipo,
            entrega.direccion,
            medio.id,
            estado,
            pedido_existente=anterior,
        )
        if entrega.direccion:
            conv.cliente.ultima_direccion = entrega.direccion
        conv.contexto_json.pop("direccion_por_confirmar", None)
        conv.contexto_json.pop("edicion_pedido_id", None)
        conv.contexto_json.update(carrito=[], entrega={}, pedido_id=pedido.id)

        if medio.requiere_comprobante:
            conv.estado = E.ESPERANDO_PAGO
            return [mensajes.pagar_transferencia(pedido.id, medio, pedido.total)]
        conv.estado = E.PEDIDO_CONFIRMADO
        return [mensajes.pagar_al_recibir(pedido.id, medio, pedido.total, tipo)]

    def _comprobante(self, conv: Conversacion, media_url: str) -> list[Respuesta]:
        pedido = self._pedido_vigente(conv)
        if pedido is None or pedido.estado is not EstadoPedido.PENDIENTE_PAGO:
            return [
                Respuesta(texto="No hay un pago pendiente al que pueda asociar este comprobante.")
            ]
        pedido.comprobante_url = media_url  # el personal lo verifica (Fase 2)
        conv.contexto_json.pop("edicion_pedido_id", None)
        conv.contexto_json.update(carrito=[], entrega={}, pedido_id=pedido.id)
        conv.estado = E.PEDIDO_CONFIRMADO
        return [mensajes.comprobante_recibido()]

    def _cancelar(self, conv: Conversacion) -> list[Respuesta]:
        if conv.contexto_json.get("edicion_pedido_id"):
            pedido = self._pedido_vigente(conv)
            if (
                pedido is None
                or pedido.estado is not EstadoPedido.PENDIENTE_PAGO
                or not editable(pedido)
            ):
                return self._a_humano(conv)
            pedido.estado = EstadoPedido.CANCELADO
            conv.contexto_json.pop("edicion_pedido_id", None)
        if conv.estado is E.PEDIDO_CONFIRMADO:
            return self._a_humano(conv)  # ya mandó comprobante o se está preparando
        if conv.estado is E.ESPERANDO_PAGO:
            pedido = self._pedido_vigente(conv)
            if pedido is None or not editable(pedido):
                return self._a_humano(conv)
            pedido.estado = EstadoPedido.CANCELADO
        conv.contexto_json.pop("direccion_por_confirmar", None)
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
        if conv.estado is E.DATOS_ENTREGA:
            conv.contexto_json["fallos"] = 0
            entrega = DatosEntrega.model_validate(conv.contexto_json.get("entrega", {}))
            if entrega.direccion or entrega.tipo is TipoEntrega.RECOGER:
                return self._paso_actual(conv, leer_menu(self.session))
            if conv.contexto_json.get("direccion_por_confirmar"):
                return [mensajes.confirmar_direccion(conv.contexto_json["direccion_por_confirmar"])]
            return [mensajes.aclarar_direccion()]
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
            select(Conversacion)
            .where(Conversacion.canal == e.canal, Conversacion.id_externo == e.id_externo)
            .with_for_update()
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
