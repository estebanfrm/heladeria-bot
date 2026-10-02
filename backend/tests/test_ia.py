"""Servicio de IA (paso 4 de la Fase 1): prompt, proveedores y JSON validado. Sin red."""

import json

import httpx
import pytest

from app.config import Settings
from app.enums import EstadoConversacion
from app.ia.casos import CASOS, PEDIDO_COMPLETO, PEDIDO_INICIAL
from app.ia.interpretacion import Intencion
from app.ia.prompt import construir_prompt, describir_menu
from app.ia.proveedores import (
    ErrorIA,
    ProveedorCompatibleOpenAI,
    ProveedorFalso,
    crear_proveedor,
)
from app.ia.servicio import RespuestaIAInvalida, interpretar, leer_respuesta
from app.pedidos.carrito import validar_carrito

# --- Prompt -------------------------------------------------------------------------


def test_menu_del_prompt_tiene_codigos_y_no_precios(menu_demo):
    texto = describir_menu(menu_demo)

    assert "- copa_queso: Copa queso → sabor ×2 de [sabores], salsa ×1 de [salsas_base]" in texto
    assert "- granizado_cafe: Granizado de café → nada que elegir" in texto
    assert "frutos_rojos=Frutos rojos" in texto
    assert "- topping_extra: Topping adicional (elige 1 de [toppings_waffle])" in texto
    precios = {p.precio for p in menu_demo.productos} | {a.precio for a in menu_demo.adicionales}
    assert not any(str(precio) in texto for precio in precios)
    assert "300 000 0000" not in texto  # tampoco números de cuenta


def test_prompt_incluye_estado_carrito_y_lo_que_falta(menu_demo):
    sistema, usuario = construir_prompt(
        menu_demo,
        "copa: frutos rojos y maní",
        PEDIDO_INICIAL,
        EstadoConversacion.COMPLETANDO_OPCIONES,
    )

    assert "Heladería Demo" in sistema and "PRODUCTOS" in sistema
    assert "ESTADO: COMPLETANDO_OPCIONES" in usuario
    assert '"producto":"copa_queso"' in usuario
    assert "Copa queso: salsa ×1, topping ×1" in usuario
    assert "Banana split: sabor de helado ×3, salsa ×1, topping ×1" in usuario
    assert usuario.endswith('MENSAJE DEL CLIENTE: """copa: frutos rojos y maní"""')


# --- Leer la respuesta ------------------------------------------------------------


def test_lee_json_aunque_venga_en_bloque_de_codigo():
    texto = 'Claro:\n```json\n{"intencion": "humano"}\n```'
    assert leer_respuesta(texto).intencion is Intencion.HUMANO


@pytest.mark.parametrize(
    "texto",
    [
        "No entendí el mensaje",
        "{no es json}",
        '{"intencion": "bailar"}',
        '{"intencion": "pedido", "items": [{"producto": "copa_queso", "cantidad": 0}]}',
        '{"intencion": "pedido", "items": [{"producto": "x", "opciones": {"salsita": ["y"]}}]}',
    ],
)
def test_respuesta_invalida_se_rechaza(texto):
    with pytest.raises(RespuestaIAInvalida):
        leer_respuesta(texto)


def test_un_precio_inventado_por_la_ia_no_se_usa(menu_demo):
    texto = json.dumps(
        {
            "intencion": "pedido",
            "total": 1000,
            "items": [{"producto": "copa_queso", "precio": 1, "opciones": {"sabor": ["brownie"]}}],
        }
    )
    resultado = validar_carrito(menu_demo, leer_respuesta(texto).items)
    assert resultado.total == 12000


# --- Proveedor compatible con OpenAI (sin red: transporte simulado) ------------------


def _proveedor(manejador) -> ProveedorCompatibleOpenAI:
    cliente = httpx.Client(
        base_url="https://api.groq.com/openai/v1",
        headers={"Authorization": "Bearer clave-de-prueba"},
        transport=httpx.MockTransport(manejador),
    )
    return ProveedorCompatibleOpenAI("ignorada", "modelo-x", cliente=cliente)


def test_proveedor_envia_chat_completions_en_modo_json():
    recibido = {}

    def manejador(request: httpx.Request) -> httpx.Response:
        recibido["url"] = str(request.url)
        recibido["auth"] = request.headers["authorization"]
        recibido["cuerpo"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"x": 1}'}}]})

    assert _proveedor(manejador).completar_json("sis", "usu") == '{"x": 1}'
    assert recibido["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert recibido["auth"] == "Bearer clave-de-prueba"
    cuerpo = recibido["cuerpo"]
    assert cuerpo["model"] == "modelo-x"
    assert cuerpo["temperature"] == 0
    assert cuerpo["response_format"] == {"type": "json_object"}
    assert [m["role"] for m in cuerpo["messages"]] == ["system", "user"]


@pytest.mark.parametrize(
    ("respuesta", "mensaje"),
    [
        (httpx.Response(429, text="rate limit"), "respondió 429"),
        (httpx.Response(200, json={"choices": []}), "formato inesperado"),
        (
            httpx.Response(200, json={"choices": [{"message": {"content": None}}]}),
            "no devolvió texto",
        ),
    ],
)
def test_errores_del_proveedor(respuesta, mensaje):
    with pytest.raises(ErrorIA, match=mensaje):
        _proveedor(lambda _req: respuesta).completar_json("s", "u")


def test_sin_conexion_es_error_ia():
    def manejador(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin red", request=request)

    with pytest.raises(ErrorIA, match="No se pudo contactar"):
        _proveedor(manejador).completar_json("s", "u")


# --- Fábrica según .env -------------------------------------------------------------


def _config(**valores) -> Settings:
    return Settings(_env_file=None, **{"ia_model": "m", "ia_api_key": "k", **valores})


@pytest.mark.parametrize(
    ("proveedor", "url"),
    [
        ("gemini", "https://generativelanguage.googleapis.com/v1beta/openai/"),
        ("groq", "https://api.groq.com/openai/v1/"),
        ("openai", "https://api.openai.com/v1/"),
    ],
)
def test_crear_proveedor_usa_la_url_de_cada_uno(proveedor, url):
    creado = crear_proveedor(_config(ia_provider=proveedor))
    assert str(creado._cliente.base_url) == url


def test_ollama_no_necesita_api_key_y_la_url_se_puede_cambiar():
    creado = crear_proveedor(
        _config(
            ia_provider="ollama", ia_api_key="", ia_base_url="http://host.docker.internal:11434/v1"
        )
    )
    assert str(creado._cliente.base_url) == "http://host.docker.internal:11434/v1/"


@pytest.mark.parametrize(
    ("valores", "mensaje"),
    [
        ({"ia_provider": "anthropic"}, "aún no está soportado"),
        ({"ia_provider": "groq", "ia_model": ""}, "Falta IA_MODEL"),
        ({"ia_provider": "groq", "ia_api_key": ""}, "Falta IA_API_KEY"),
    ],
)
def test_configuracion_invalida(valores, mensaje):
    with pytest.raises(ValueError, match=mensaje):
        crear_proveedor(_config(**valores))


# --- Casos del chat real con el proveedor falso -------------------------------------


@pytest.mark.parametrize("caso", CASOS, ids=lambda c: c.nombre)
def test_casos_del_chat_real(menu_demo, caso):
    """La respuesta ideal de cada caso pasa su verificación (valida el flujo y los casos)."""
    falso = ProveedorFalso([caso.ideal.model_dump_json()])

    resultado = interpretar(falso, menu_demo, caso.mensaje, caso.carrito, caso.estado)

    assert caso.verificar(resultado, menu_demo) is None
    assert caso.mensaje in falso.llamadas[0][1]


def test_flujo_real_texto_a_24000(menu_demo):
    """Primer mensaje → faltantes; respuesta del cliente → carrito completo de $24.000."""
    falso = ProveedorFalso([CASOS[1].ideal.model_dump_json(), CASOS[2].ideal.model_dump_json()])

    primero = interpretar(falso, menu_demo, CASOS[1].mensaje)
    assert not validar_carrito(menu_demo, primero.items).completo

    segundo = interpretar(
        falso, menu_demo, CASOS[2].mensaje, primero.items, EstadoConversacion.COMPLETANDO_OPCIONES
    )
    final = validar_carrito(menu_demo, segundo.items)
    assert final.completo and final.total == 24000
    assert segundo.items == PEDIDO_COMPLETO
