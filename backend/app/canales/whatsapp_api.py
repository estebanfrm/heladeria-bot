"""Cliente de la WhatsApp Cloud API (Graph API de Meta): envía las respuestas del motor.

El motor no sabe de WhatsApp: devuelve texto + botones genéricos. Aquí se traducen al
formato de la Cloud API respetando sus límites (D7: botones y listas para opciones cerradas).
"""

import logging
from typing import Protocol

import httpx

from app.config import Settings
from app.conversacion.mensajes import Respuesta

logger = logging.getLogger(__name__)

URL_GRAPH = "https://graph.facebook.com"

# Límites de la Cloud API para mensajes interactivos
MAX_TEXTO = 4096
MAX_CUERPO_INTERACTIVO = 1024
MAX_BOTONES = 3
MAX_TITULO_BOTON = 20
MAX_FILAS_LISTA = 10
MAX_TITULO_FILA = 24


class ErrorWhatsApp(RuntimeError):
    pass


def construir_mensajes(telefono: str, respuesta: Respuesta) -> list[dict]:
    """Respuesta del motor → mensajes de la Cloud API (texto, botones ≤3 o lista ≤10)."""
    base = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": telefono}
    texto = respuesta.texto[:MAX_TEXTO]
    botones = respuesta.botones[:MAX_FILAS_LISTA]
    if not botones:
        return [base | {"type": "text", "text": {"body": texto, "preview_url": False}}]

    mensajes = []
    if len(texto) > MAX_CUERPO_INTERACTIVO:  # el texto va aparte y los botones después
        mensajes.append(base | {"type": "text", "text": {"body": texto, "preview_url": False}})
        texto = "Elige una opción:"

    if len(botones) <= MAX_BOTONES:
        interactivo = {
            "type": "button",
            "body": {"text": texto},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": b.id, "title": b.titulo[:MAX_TITULO_BOTON]}}
                    for b in botones
                ]
            },
        }
    else:
        interactivo = {
            "type": "list",
            "body": {"text": texto},
            "action": {
                "button": "Ver opciones",
                "sections": [
                    {
                        "title": "Opciones",
                        "rows": [
                            {"id": b.id, "title": b.titulo[:MAX_TITULO_FILA]} for b in botones
                        ],
                    }
                ],
            },
        }
    mensajes.append(base | {"type": "interactive", "interactive": interactivo})
    return mensajes


class EnviadorWhatsApp(Protocol):
    def enviar(self, telefono: str, respuesta: Respuesta) -> None: ...


class ClienteWhatsApp:
    def __init__(
        self,
        phone_number_id: str,
        token: str,
        version: str = "v26.0",
        timeout: float = 10.0,
        cliente: httpx.Client | None = None,  # inyectable en tests
    ):
        self.phone_number_id = phone_number_id
        self._cliente = cliente or httpx.Client(
            base_url=f"{URL_GRAPH}/{version}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )

    def enviar(self, telefono: str, respuesta: Respuesta) -> None:
        for mensaje in construir_mensajes(telefono, respuesta):
            try:
                r = self._cliente.post(f"{self.phone_number_id}/messages", json=mensaje)
            except httpx.HTTPError as e:
                raise ErrorWhatsApp(f"No se pudo contactar a la Cloud API: {e!r}") from e
            if r.is_error:
                raise ErrorWhatsApp(f"La Cloud API respondió {r.status_code}: {r.text[:300]}")


class EnviadorNoConfigurado:
    """Sin credenciales de WhatsApp: no se envía nada y queda el aviso en el log."""

    def __init__(self, motivo: str):
        self.motivo = motivo

    def enviar(self, telefono: str, respuesta: Respuesta) -> None:
        logger.warning("WhatsApp no configurado (%s): no se envió a %s", self.motivo, telefono)


def crear_enviador(config: Settings) -> EnviadorWhatsApp:
    faltan = [
        nombre
        for nombre, valor in (
            ("WA_PHONE_NUMBER_ID", config.wa_phone_number_id),
            ("WA_ACCESS_TOKEN", config.wa_access_token),
        )
        if not valor
    ]
    if faltan:
        return EnviadorNoConfigurado("faltan " + ", ".join(faltan))
    return ClienteWhatsApp(config.wa_phone_number_id, config.wa_access_token, config.wa_api_version)
