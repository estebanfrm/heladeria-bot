"""Endpoint /chat (paso 6 de la Fase 1): el chat web sobre el motor, por HTTP."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.canales.web import get_proveedor
from app.config import settings
from app.db import get_db
from app.enums import Canal, EstadoPedido, TipoEntrega
from app.ia.casos import CASOS
from app.ia.interpretacion import Intencion, Interpretacion
from app.ia.proveedores import ProveedorFalso, ProveedorNoConfigurado
from app.main import app
from app.menu.carga import aplicar_menu
from app.models import Mensaje, Pedido

CASO = {c.nombre: c for c in CASOS}


@pytest.fixture
def falso() -> ProveedorFalso:
    return ProveedorFalso([])


@pytest.fixture
def api(db, falso):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_proveedor] = lambda: falso
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def con_menu(db, menu_demo):
    aplicar_menu(db, menu_demo)


def _enviar(api, falso, ia: Interpretacion | None = None, **cuerpo) -> dict:
    if ia is not None:
        falso.respuestas.append(ia.model_dump_json())
    respuesta = api.post("/chat", json=cuerpo)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def test_conversacion_real_por_el_chat_web(db, api, falso, con_menu):
    r = _enviar(api, falso, Interpretacion(intencion=Intencion.SALUDO), texto="Hola buenas noches")
    sesion = r["sesion"]
    assert r["respuestas"][0]["texto"].startswith("¡Hola! 🍦 Bienvenido a Heladería Demo")
    assert [b["id"] for b in r["respuestas"][0]["botones"]] == ["menu", "pedir", "humano"]

    caso = CASO["pedido_inicial"]
    r = _enviar(api, falso, caso.ideal, sesion=sesion, texto=caso.mensaje)
    assert "• Salsa (elige 1): frutos rojos / maracuyá / lecherita" in r["respuestas"][0]["texto"]

    caso = CASO["completar_opciones"]
    r = _enviar(api, falso, caso.ideal, sesion=sesion, texto=caso.mensaje)
    assert r["respuestas"][0]["texto"].endswith("*Total: $24.000*")

    _enviar(api, falso, sesion=sesion, boton="confirmar")
    _enviar(api, falso, sesion=sesion, boton="entrega:recoger")
    r = _enviar(api, falso, sesion=sesion, boton="pago:efectivo")
    assert "Total a pagar al recogerlo: *$24.000*" in r["respuestas"][0]["texto"]

    pedido = db.scalars(select(Pedido)).one()
    assert (pedido.total, pedido.estado) == (24000, EstadoPedido.EN_PREPARACION)
    assert pedido.tipo_entrega is TipoEntrega.RECOGER
    assert pedido.conversacion.canal is Canal.WEB
    assert pedido.conversacion.id_externo == sesion
    assert pedido.cliente.telefono is None


def test_cada_visitante_recibe_su_sesion(api, falso, con_menu):
    primera = _enviar(api, falso, boton="menu")["sesion"]
    segunda = _enviar(api, falso, boton="menu")["sesion"]

    assert primera != segunda
    assert _enviar(api, falso, sesion=primera, boton="menu")["sesion"] == primera


def test_limite_de_mensajes_por_sesion(db, api, falso, con_menu, monkeypatch):
    monkeypatch.setattr(settings, "web_chat_max_msgs_per_session", 2)
    sesion = _enviar(api, falso, boton="menu")["sesion"]
    _enviar(api, falso, sesion=sesion, boton="menu")

    falso.respuestas.append(Interpretacion(intencion=Intencion.SALUDO).model_dump_json())
    respuesta = api.post("/chat", json={"sesion": sesion, "texto": "una copa más"})

    assert respuesta.status_code == 429
    assert "límite de 2 mensajes" in respuesta.json()["detail"]
    assert falso.llamadas == []  # no se gastó una llamada a la IA
    assert db.scalar(select(func.count()).select_from(Mensaje)) == 4  # ni se guardó el mensaje
    assert _enviar(api, falso, boton="menu")  # otra sesión sí puede escribir


@pytest.mark.parametrize(
    "cuerpo",
    [
        {},
        {"texto": "   "},
        {"texto": "x" * 501},
        {"sesion": "corta", "texto": "hola"},
        {"sesion": "con espacios 123", "texto": "hola"},
    ],
)
def test_entradas_invalidas(api, cuerpo):
    assert api.post("/chat", json=cuerpo).status_code == 422


def test_sin_ia_configurada_los_botones_siguen_funcionando(api, con_menu):
    app.dependency_overrides[get_proveedor] = lambda: ProveedorNoConfigurado("Falta IA_API_KEY")

    carta = api.post("/chat", json={"boton": "menu"}).json()
    assert "• Copa queso — $12.000" in carta["respuestas"][0]["texto"]

    texto = api.post("/chat", json={"sesion": carta["sesion"], "texto": "una copa queso"}).json()
    assert texto["respuestas"][0]["texto"].startswith("No te entendí")


def test_sin_menu_cargado_responde_503(api):
    respuesta = api.post("/chat", json={"boton": "menu"})

    assert respuesta.status_code == 503
    assert "El menú no está cargado" in respuesta.json()["detail"]


def test_health_informa_el_estado_de_la_ia(api):
    app.dependency_overrides.clear()
    get_proveedor.cache_clear()
    try:
        cuerpo = TestClient(app).get("/health").json()
    finally:
        get_proveedor.cache_clear()

    assert cuerpo["status"] == "ok"
    assert "ia" in cuerpo
