"""Documentos reales en la Cloud API; HTTP simulado, sin enviar a destinatarios."""

import json

import httpx
import pytest

from app.canales.whatsapp_api import ClienteWhatsApp, ErrorWhatsApp
from app.conversacion.mensajes import Respuesta


def test_subir_pdf_y_enviar_documento_reutiliza_media_y_detecta_cambio(tmp_path):
    pdf = tmp_path / "menu.pdf"
    pdf.write_bytes(b"%PDF-1.7\ncontenido original")
    subidas, mensajes = [], []

    def responder(request):
        if request.url.path.endswith("/media"):
            subidas.append(request.content)
            assert b"application/pdf" in request.content
            assert pdf.read_bytes() in request.content
            return httpx.Response(200, json={"id": f"pdf-{len(subidas)}"})
        mensajes.append(json.loads(request.content))
        return httpx.Response(200, json={"messages": [{"id": "wamid.prueba"}]})

    with httpx.Client(
        base_url="https://graph.facebook.com/v26.0", transport=httpx.MockTransport(responder)
    ) as http:
        wa = ClienteWhatsApp("numero", "token", cliente=http, menu_pdf_file=pdf)
        r = Respuesta(texto="Aquí está el menú", documento="menu")
        wa.enviar("destinatario", r)
        wa.enviar("destinatario", r)
        assert len(subidas) == 1
        assert all(m["type"] == "document" and "text" not in m for m in mensajes)
        assert mensajes[0]["document"] == {
            "id": "pdf-1",
            "filename": "menu.pdf",
            "caption": "Aquí está el menú",
        }
        pdf.write_bytes(b"%PDF-1.7\ncontenido actualizado y mas largo")
        wa.enviar("destinatario", r)
        assert len(subidas) == 2
        assert mensajes[-1]["document"]["id"] == "pdf-2"


@pytest.mark.parametrize("estado", [400, 500])
def test_error_al_subir_no_envia_menu_de_texto(tmp_path, estado):
    pdf = tmp_path / "menu.pdf"
    pdf.write_bytes(b"%PDF-1.7\nprueba")
    rutas = []

    def responder(request):
        rutas.append(request.url.path)
        return httpx.Response(estado, json={"error": {"message": "upload falló"}})

    with httpx.Client(
        base_url="https://graph.facebook.com/v26.0", transport=httpx.MockTransport(responder)
    ) as http:
        wa = ClienteWhatsApp("numero", "token", cliente=http, menu_pdf_file=pdf)
        with pytest.raises(ErrorWhatsApp, match="Meta rechazó el PDF"):
            wa.enviar("destinatario", Respuesta(texto="Menú", documento="menu"))
        assert rutas == ["/v26.0/numero/media"]


def test_archivo_que_no_es_pdf_no_se_sube(tmp_path):
    pdf = tmp_path / "menu.pdf"
    pdf.write_text("no es un PDF")

    def responder(request):
        pytest.fail("No debe contactar a Meta con un archivo inválido")

    with httpx.Client(
        base_url="https://graph.facebook.com/v26.0", transport=httpx.MockTransport(responder)
    ) as http:
        wa = ClienteWhatsApp("numero", "token", cliente=http, menu_pdf_file=pdf)
        with pytest.raises(ErrorWhatsApp, match="no es un PDF"):
            wa.enviar("destinatario", Respuesta(texto="Menú", documento="menu"))
