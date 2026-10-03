"""Verificación y firma del webhook que se expone durante las pruebas con Meta."""

import hashlib
import hmac

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.whatsapp_demo import app


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(settings, "wa_verify_token", "token-prueba")
    monkeypatch.setattr(settings, "wa_app_secret", "secreto-prueba")
    with TestClient(app) as cliente:
        yield cliente


def test_verificacion_devuelve_desafio_y_rechaza_token_incorrecto(api):
    parametros = {
        "hub.mode": "subscribe",
        "hub.verify_token": "token-prueba",
        "hub.challenge": "123456",
    }
    respuesta = api.get("/webhook/whatsapp", params=parametros)
    assert respuesta.status_code == 200
    assert respuesta.text == "123456"
    parametros["hub.verify_token"] = "incorrecto"
    assert api.get("/webhook/whatsapp", params=parametros).status_code == 403


def test_firma_valida_y_cuerpo_alterado(api):
    cuerpo = b'{"object":"whatsapp_business_account","entry":[]}'
    firma = "sha256=" + hmac.new(b"secreto-prueba", cuerpo, hashlib.sha256).hexdigest()
    cabeceras = {"X-Hub-Signature-256": firma, "Content-Type": "application/json"}
    respuesta = api.post("/webhook/whatsapp", content=cuerpo, headers=cabeceras)
    assert respuesta.status_code == 200
    assert respuesta.json() == {"recibidos": 0}
    assert (
        api.post("/webhook/whatsapp", content=cuerpo + b" ", headers=cabeceras).status_code == 403
    )
    assert api.post("/webhook/whatsapp", content=cuerpo).status_code == 403


@pytest.mark.parametrize("ruta", ["/", "/chat", "/menu", "/docs", "/openapi.json"])
def test_tunel_no_expone_otros_endpoints(api, ruta):
    assert api.get(ruta).status_code == 404
    assert api.post(ruta, json={}).status_code == 404
