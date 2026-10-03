"""Cliente de la WhatsApp Cloud API (Graph API de Meta): envía las respuestas del motor.

El motor no sabe de WhatsApp: devuelve texto + botones genéricos. Aquí se traducen al
formato de la Cloud API respetando sus límites (D7: botones y listas para opciones cerradas).
"""

import logging
from pathlib import Path
from threading import Lock
from time import monotonic
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


def construir_mensajes(
    telefono: str, respuesta: Respuesta, documento_id: str | None = None
) -> list[dict]:
    """Respuesta del motor → mensajes de la Cloud API (texto, botones ≤3 o lista ≤10)."""
    base = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": telefono}
    if respuesta.documento:
        if not documento_id:
            raise ErrorWhatsApp("Falta el ID del PDF del menú")
        return [
            base
            | {
                "type": "document",
                "document": {
                    "id": documento_id,
                    "filename": "menu.pdf",
                    "caption": respuesta.texto[:MAX_CUERPO_INTERACTIVO],
                },
            }
        ]
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
        menu_pdf_file: Path | None = None,
    ):
        self.phone_number_id = phone_number_id
        self.menu_pdf_file = menu_pdf_file
        self._media_menu: tuple[tuple[int, int], str, float] | None = None
        self._media_lock = Lock()
        self._cliente = cliente or httpx.Client(
            base_url=f"{URL_GRAPH}/{version}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )

    def enviar(self, telefono: str, respuesta: Respuesta) -> None:
        documento_id = self._subir_menu() if respuesta.documento else None
        for mensaje in construir_mensajes(telefono, respuesta, documento_id):
            try:
                r = self._cliente.post(f"{self.phone_number_id}/messages", json=mensaje)
            except httpx.HTTPError as e:
                raise ErrorWhatsApp(f"No se pudo contactar a la Cloud API: {e!r}") from e
            if r.is_error:
                raise ErrorWhatsApp(f"La Cloud API respondió {r.status_code}: {r.text[:300]}")

    def _subir_menu(self) -> str:
        """Sube el PDF a Meta; reutiliza el ID durante un día o hasta que cambie el archivo."""
        ruta = self.menu_pdf_file
        if ruta is None:
            raise ErrorWhatsApp("Falta configurar WA_MENU_PDF_FILE")
        with self._media_lock:
            try:
                stat = ruta.stat()
                version = (stat.st_size, stat.st_mtime_ns)
                if stat.st_size > 100 * 1024 * 1024:
                    raise ErrorWhatsApp("El PDF del menú supera 100 MB")
                if self._media_menu:
                    anterior, media_id, vence = self._media_menu
                    if anterior == version and monotonic() < vence:
                        return media_id
                with ruta.open("rb") as archivo:
                    if archivo.read(5) != b"%PDF-":
                        raise ErrorWhatsApp("El archivo del menú no es un PDF")
                    archivo.seek(0)
                    r = self._cliente.post(
                        f"{self.phone_number_id}/media",
                        data={"messaging_product": "whatsapp", "type": "application/pdf"},
                        files={"file": ("menu.pdf", archivo, "application/pdf")},
                        timeout=60,
                    )
            except (OSError, httpx.HTTPError) as e:
                raise ErrorWhatsApp("No se pudo subir el PDF del menú a Meta") from e
            if r.is_error:
                raise ErrorWhatsApp(f"Meta rechazó el PDF ({r.status_code}): {r.text[:300]}")
            try:
                media_id = r.json()["id"]
                if not isinstance(media_id, str) or not media_id:
                    raise ValueError("ID de medio vacío")
            except (KeyError, ValueError, TypeError) as e:
                raise ErrorWhatsApp("Meta no devolvió un ID válido para el PDF") from e
            self._media_menu = (version, media_id, monotonic() + 86400)
            return media_id


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
    return ClienteWhatsApp(
        config.wa_phone_number_id,
        config.wa_access_token,
        config.wa_api_version,
        menu_pdf_file=config.wa_menu_pdf_file,
    )
