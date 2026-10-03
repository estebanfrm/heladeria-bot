"""Motor de conversación (paso 5 de la Fase 1): la sección 7 de PLANEACION.md de punta a punta.

La IA es un ProveedorFalso con respuestas guionadas; todo lo demás es real (BD, carrito, reglas).
"""

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.conversacion.motor import Entrada, Motor
from app.enums import Canal, EstadoConversacion, EstadoPedido, ModoConversacion, TipoEntrega
from app.ia.casos import CASOS, PEDIDO_COMPLETO
from app.ia.interpretacion import DatosEntrega, Intencion, Interpretacion
from app.ia.proveedores import ProveedorFalso
from app.menu.carga import aplicar_menu
from app.models import Conversacion, Mensaje, Negocio, Pedido, Producto
from app.pedidos.carrito import ItemSolicitado

CASO = {c.nombre: c for c in CASOS}
WA = "573000000000"
E = EstadoConversacion


@pytest.fixture
def chat(db, menu_demo, monkeypatch):
    """chat(texto, ia=..., boton=..., media=...) → respuestas del bot."""
    aplicar_menu(db, menu_demo)
    monkeypatch.setattr(settings, "wa_menu_pdf_file", None)
    falso = ProveedorFalso([])
    motor = Motor(db, falso)

    def decir(
        texto: str = "",
        *,
        ia: Interpretacion | str | None = None,
        boton: str | None = None,
        media: str | None = None,
        canal: Canal = Canal.WHATSAPP,
        id_externo: str = WA,
    ):
        if ia is not None:
            falso.respuestas.append(ia if isinstance(ia, str) else ia.model_dump_json())
        respuestas = motor.procesar(
            Entrada(canal=canal, id_externo=id_externo, texto=texto, boton=boton, media_url=media)
        )
        assert not falso.respuestas, "la IA no se usó y se esperaba"
        return respuestas

    decir.falso = falso
    return decir


def _conv(db, id_externo: str = WA) -> Conversacion:
    return db.scalars(select(Conversacion).where(Conversacion.id_externo == id_externo)).one()


def _pedir(intencion: Intencion = Intencion.PEDIDO, **campos) -> Interpretacion:
    return Interpretacion(intencion=intencion, **campos)


def _hasta_resumen(chat):
    chat("una copa queso y un banana split…", ia=_pedir(items=PEDIDO_COMPLETO))


def _hasta_esperar_pago(chat):
    _hasta_resumen(chat)
    chat(boton="confirmar")
    chat(CASO["entrega_y_pago"].mensaje, ia=CASO["entrega_y_pago"].ideal)


# --- El chat real de punta a punta ---------------------------------------------------


def test_conversacion_real_completa(db, chat):
    r = chat("Hola buenas noches", ia=_pedir(Intencion.SALUDO))
    assert r[0].texto == "¡Hola! 🍦 Bienvenido a Heladería Demo. ¿Qué se te antoja?"
    assert [b.id for b in r[0].botones] == ["menu", "pedir", "humano"]

    r = chat(CASO["pedido_inicial"].mensaje, ia=CASO["pedido_inicial"].ideal)
    assert "*Copa queso* (brownie, fresa)" in r[0].texto
    assert "Elige salsa: 1 de 1" in r[0].texto and r[0].lista
    assert {b.titulo for b in r[0].botones} >= {"Frutos rojos", "Maracuyá", "Lecherita"}
    assert "Banana split" not in r[0].texto  # una elección por paso
    assert _conv(db).estado is E.COMPLETANDO_OPCIONES

    r = chat(CASO["completar_opciones"].mensaje, ia=CASO["completar_opciones"].ideal)
    assert r[0].texto == (
        "📝 *Tu pedido:*\n"
        "1× Copa queso — brownie, fresa · frutos rojos · maní — $12.000\n"
        "1× Banana split — brownie, vainilla chips, brownie · frutos rojos · oreo triturado"
        " — $12.000\n"
        "*Total: $24.000*"
    )
    assert [b.id for b in r[0].botones[:3]] == ["confirmar", "agregar", "cambiar"]
    assert r[0].botones[3].titulo == "Elegir de nuevo"

    r = chat(boton="confirmar")
    assert r[0].texto.startswith("¿A qué dirección lo enviamos y cómo pagas?")
    assert "pago:nequi" in [b.id for b in r[0].botones]

    r = chat(CASO["entrega_y_pago"].mensaje, ia=CASO["entrega_y_pago"].ideal)
    assert "Envía *$24.000* al *Nequi 300 000 0000* a nombre de *Heladería Demo*" in r[0].texto
    assert _conv(db).estado is E.ESPERANDO_PAGO

    r = chat(media="https://ejemplo.test/comprobante.jpg")
    assert r[0].texto.startswith("¡Recibido!")

    pedido = db.scalars(select(Pedido)).one()
    assert (pedido.total, pedido.estado) == (24000, EstadoPedido.PENDIENTE_PAGO)
    assert (pedido.tipo_entrega, pedido.direccion) == (TipoEntrega.DOMICILIO, "Calle Falsa #12-34")
    assert pedido.medio_pago.codigo == "nequi"
    assert pedido.comprobante_url == "https://ejemplo.test/comprobante.jpg"
    assert [o.nombre for o in pedido.items[1].opciones] == [
        "Brownie",
        "Vainilla chips",
        "Brownie",
        "Frutos rojos",
        "Oreo triturado",
    ]
    conv = _conv(db)
    assert conv.estado is E.PEDIDO_CONFIRMADO
    assert conv.cliente.telefono == WA
    assert conv.cliente.ultima_direccion == "Calle Falsa #12-34"
    assert db.scalar(select(func.count()).select_from(Mensaje)) == 12  # 6 del cliente, 6 del bot


# --- Entrega y pago --------------------------------------------------------------------


def test_recoger_y_efectivo_pasa_directo_a_preparacion(db, chat):
    _hasta_resumen(chat)
    chat(boton="confirmar")

    r = chat(boton="entrega:recoger")
    assert r[0].texto == "¿Cómo vas a pagar?"
    assert "entrega:recoger" not in [b.id for b in r[0].botones]

    r = chat(boton="pago:efectivo")
    assert "ya está en preparación" in r[0].texto
    assert "Total a pagar al recogerlo: *$24.000*" in r[0].texto
    pedido = db.scalars(select(Pedido)).one()
    assert (pedido.estado, pedido.tipo_entrega) == (
        EstadoPedido.EN_PREPARACION,
        TipoEntrega.RECOGER,
    )
    assert (pedido.direccion, pedido.domicilio) == (None, 0)
    assert _conv(db).estado is E.PEDIDO_CONFIRMADO


def test_domicilio_se_avisa_y_se_cobra(db, chat):
    db.scalar(select(Negocio)).costo_domicilio = 3000
    _hasta_resumen(chat)

    r = chat(boton="confirmar")
    assert "El domicilio cuesta $3.000." in r[0].texto

    r = chat(CASO["entrega_y_pago"].mensaje, ia=CASO["entrega_y_pago"].ideal)
    assert "Envía *$27.000*" in r[0].texto
    pedido = db.scalars(select(Pedido)).one()
    assert (pedido.subtotal, pedido.domicilio, pedido.total) == (24000, 3000, 27000)


def test_entrega_por_partes_y_medio_de_pago_invalido(db, chat):
    _hasta_resumen(chat)
    chat(boton="confirmar")

    r = chat(
        "Calle Falsa 123",
        ia=_pedir(Intencion.ENTREGA, entrega=DatosEntrega(direccion="Calle Falsa 123")),
    )
    assert r[0].texto == "¿Cómo vas a pagar?"

    r = chat(
        "con bitcoin", ia=_pedir(Intencion.ENTREGA, entrega=DatosEntrega(medio_pago="bitcoin"))
    )
    assert r[0].texto.startswith("⚠️ No recibimos «bitcoin». Puedes pagar con: Nequi, Daviplata")

    r = chat(boton="pago:daviplata")
    assert "al *Daviplata 300 000 0000*" in r[0].texto
    assert db.scalars(select(Pedido)).one().direccion == "Calle Falsa 123"


def test_datos_de_entrega_al_confirmar_no_se_vuelven_a_pedir(db, chat):
    _hasta_resumen(chat)

    r = chat(
        "sí, a la Calle Falsa 123 y pago por nequi",
        ia=_pedir(
            Intencion.CONFIRMAR,
            entrega=DatosEntrega(direccion="Calle Falsa 123", medio_pago="nequi"),
        ),
    )

    assert "registrado ✅" in r[0].texto
    assert _conv(db).estado is E.ESPERANDO_PAGO


# --- Carrito desde la conversación ----------------------------------------------------


def test_problemas_del_carrito_se_explican(db, chat):
    copa = ItemSolicitado(
        producto="copa_queso",
        opciones={"sabor": ["brownie", "fresa"], "salsa": ["mora"], "topping": ["mani"]},
    )
    r = chat("copa queso con salsa de mora", ia=_pedir(items=[copa]))

    assert r[0].texto.startswith("⚠️ 'mora' no es una opción de salsa para Copa queso.")
    assert "Elige salsa: 1 de 1" in r[0].texto and r[0].lista
    assert {b.titulo for b in r[0].botones} >= {"Frutos rojos", "Maracuyá", "Lecherita"}
    assert _conv(db).estado is E.COMPLETANDO_OPCIONES


def test_agregar_desde_el_resumen(db, chat):
    _hasta_resumen(chat)

    r = chat(boton="agregar")
    assert r[0].texto == "¿Qué más quieres agregar?"
    assert _conv(db).estado is E.TOMANDO_PEDIDO

    r = chat(CASO["agregar_adicional"].mensaje, ia=CASO["agregar_adicional"].ideal)
    assert "+ topping adicional (oreo triturado) — $13.700" in r[0].texto
    assert "*Total: $25.700*" in r[0].texto


def test_menu_muestra_los_precios_de_la_bd(db, chat):
    db.scalar(select(Producto).where(Producto.codigo == "copa_queso")).precio = 13000

    r = chat(boton="menu")

    assert "• Copa queso — $13.000" in r[0].texto
    assert "• Topping adicional — $1.700" in r[0].texto


# --- Fallos, humano y cancelar --------------------------------------------------------


def test_dos_fallos_pasan_a_humano_y_el_bot_se_calla(db, chat):
    assert chat("asdfg", ia=_pedir(Intencion.OTRO))[0].texto.startswith("No te entendí")
    r = chat("qwerty", ia="esto no es JSON")  # un error de la IA también es un fallo
    assert r[0].texto.startswith("Parece que no te estoy entendiendo")
    assert _conv(db).modo is ModoConversacion.HUMANO

    llamadas = len(chat.falso.llamadas)
    assert chat("¿hola?") == []  # ahora responde una persona
    assert len(chat.falso.llamadas) == llamadas  # ni siquiera se llama a la IA
    assert db.scalar(select(func.count()).select_from(Mensaje)) == 5


def test_entender_reinicia_los_fallos(db, chat):
    chat("asdfg", ia=_pedir(Intencion.OTRO))
    chat("hola", ia=_pedir(Intencion.SALUDO))
    chat("qwerty", ia=_pedir(Intencion.OTRO))
    assert _conv(db).modo is ModoConversacion.BOT


def test_pedir_humano_con_boton(db, chat):
    r = chat(boton="humano")
    assert "pendiente de atención de una persona" in r[0].texto
    assert _conv(db).modo is ModoConversacion.HUMANO


def test_cancelar_mientras_espera_el_pago(db, chat):
    _hasta_esperar_pago(chat)

    r = chat("ya no lo quiero", ia=_pedir(Intencion.CANCELAR))

    assert r[0].texto.startswith("Listo, cancelé tu pedido")
    assert db.scalars(select(Pedido)).one().estado is EstadoPedido.CANCELADO
    assert _conv(db).estado is E.FIN


def test_cancelar_despues_del_comprobante_lo_decide_una_persona(db, chat):
    _hasta_esperar_pago(chat)
    chat(media="https://ejemplo.test/comprobante.jpg")

    r = chat("cancela todo", ia=_pedir(Intencion.CANCELAR))

    assert "pendiente de atención de una persona" in r[0].texto
    assert db.scalars(select(Pedido)).one().estado is EstadoPedido.PENDIENTE_PAGO


def test_esperando_pago_no_se_cambia_el_pedido_sin_confirmar(db, chat):
    _hasta_esperar_pago(chat)

    r = chat("agrégale un cono", ia=_pedir(items=[ItemSolicitado(producto="cono_1")]))

    assert r[0].lista and "Elige sabor de helado: 1 de 1" in r[0].texto
    assert db.scalars(select(Pedido)).one().total == 24000


def test_nuevo_pedido_despues_de_confirmado(db, chat):
    _hasta_esperar_pago(chat)
    chat(media="https://ejemplo.test/comprobante.jpg")

    r = chat(
        "ahora un granizado de lulo", ia=_pedir(items=[ItemSolicitado(producto="granizado_lulo")])
    )

    assert "1× Granizado de lulo — $8.000" in r[0].texto
    assert _conv(db).estado is E.RESUMEN
    assert db.scalars(select(Pedido)).one().total == 24000  # el anterior no cambia


# --- Canales ---------------------------------------------------------------------------


def test_chat_web_y_whatsapp_son_conversaciones_distintas(db, chat):
    chat("hola", ia=_pedir(Intencion.SALUDO), canal=Canal.WEB, id_externo="sesion-abc")
    chat("hola", ia=_pedir(Intencion.SALUDO))

    web = _conv(db, "sesion-abc")
    assert web.canal is Canal.WEB and web.cliente.telefono is None
    assert _conv(db).cliente.telefono == WA
    assert web.cliente_id != _conv(db).cliente_id


@pytest.mark.parametrize("entrada", [{"boton": "menu"}, {"texto": "menú"}])
def test_menu_pdf_solo_en_whatsapp(chat, monkeypatch, tmp_path, entrada):
    monkeypatch.setattr(settings, "wa_menu_pdf_file", tmp_path / "menu.pdf")
    r = chat(**entrada)
    assert r[0].documento == "menu"
    assert "• Copa queso" not in r[0].texto
    web = chat(**entrada, canal=Canal.WEB, id_externo="sesion-pdf")
    assert web[0].documento is None
    assert "• Copa queso" in web[0].texto


def test_direccion_del_chat_no_depende_de_ia_y_conserva_efectivo(db, chat):
    chat("granizado de lulo", ia=_pedir(items=[ItemSolicitado(producto="granizado_lulo")]))
    chat(boton="confirmar")
    chat(boton="pago:efectivo")
    llamadas = len(chat.falso.llamadas)
    r = chat("Cra 8")
    assert "Me falta el número" in r[0].texto
    assert _conv(db).modo is ModoConversacion.BOT
    assert _conv(db).contexto_json.get("fallos", 0) == 0
    assert db.scalars(select(Pedido)).all() == []
    r = chat("Cra 8 #80-70")
    assert "ya está en preparación" in r[0].texto
    pedido = db.scalars(select(Pedido)).one()
    assert pedido.direccion == "Cra 8 #80-70"
    assert pedido.tipo_entrega is TipoEntrega.DOMICILIO
    assert pedido.medio_pago.codigo == "efectivo"
    assert pedido.total == 8000
    assert len(chat.falso.llamadas) == llamadas


def test_volver_al_bot_conserva_carrito_y_pago(db, chat):
    _hasta_resumen(chat)
    chat(boton="confirmar")
    chat(boton="pago:efectivo")
    antes = dict(_conv(db).contexto_json)
    chat(boton="humano")
    assert chat("¿hola?") == []
    r = chat("bot")
    assert "¿A qué dirección" in r[0].texto
    assert _conv(db).modo is ModoConversacion.BOT
    assert _conv(db).contexto_json["carrito"] == antes["carrito"]
    assert _conv(db).contexto_json["entrega"] == antes["entrega"]


@pytest.mark.parametrize("confirmacion", [{"boton": "direccion:confirmar"}, {"texto": "sí"}])
def test_direccion_compacta_del_chat_se_confirma_sin_ia(db, chat, confirmacion):
    _hasta_resumen(chat)
    chat(boton="confirmar")
    chat(boton="pago:efectivo")
    llamadas = len(chat.falso.llamadas)
    r = chat("CRA 40 96a02")
    assert "CRA 40 96a02" in r[0].texto
    assert [b.id for b in r[0].botones] == ["direccion:confirmar", "direccion:corregir"]
    assert _conv(db).contexto_json["entrega"]["direccion"] is None
    assert db.scalars(select(Pedido)).all() == []
    chat(**confirmacion)
    pedido = db.scalars(select(Pedido)).one()
    assert pedido.direccion == "CRA 40 96a02"
    assert pedido.medio_pago.codigo == "efectivo"
    assert pedido.total == 24000
    assert "direccion_por_confirmar" not in _conv(db).contexto_json
    assert len(chat.falso.llamadas) == llamadas


@pytest.mark.parametrize(
    "direccion",
    [
        "CRA 40 #96A-02",
        "Cra. 40 96a 02",
        "Carrera 40 96A–02 apartamento 301",
        "Calle 96A #40-02, barrio El Caney",
        "CRA 40 96a02",
    ],
)
def test_corregir_direccion_compacta_y_aceptar_variantes(db, chat, direccion):
    _hasta_resumen(chat)
    chat(boton="confirmar")
    chat(boton="pago:efectivo")
    llamadas = len(chat.falso.llamadas)
    chat("CRA 40 96a02")
    r = chat(boton="direccion:corregir")
    assert "dirección completa" in r[0].texto
    assert "direccion_por_confirmar" not in _conv(db).contexto_json
    chat(direccion)
    if _conv(db).contexto_json.get("direccion_por_confirmar"):
        chat(boton="direccion:confirmar")
    assert db.scalars(select(Pedido)).one().direccion == direccion
    assert len(chat.falso.llamadas) == llamadas


@pytest.mark.parametrize("direccion", ["CRA 40", "CRA 40 9602", "CRA 40 #96A-"])
def test_direccion_incompleta_pide_aclarar_sin_humano_ni_pedido(db, chat, direccion):
    _hasta_resumen(chat)
    chat(boton="confirmar")
    chat(boton="pago:efectivo")
    llamadas = len(chat.falso.llamadas)
    for _ in range(3):
        r = chat(direccion)
        assert "dirección" in r[0].texto
    assert _conv(db).modo is ModoConversacion.BOT
    assert _conv(db).contexto_json["fallos"] == 0
    assert db.scalars(select(Pedido)).all() == []
    assert len(chat.falso.llamadas) == llamadas


def test_ia_invalida_en_entrega_pide_direccion_sin_perder_carrito(db, chat):
    _hasta_resumen(chat)
    chat(boton="confirmar")
    chat(boton="pago:efectivo")
    carrito = _conv(db).contexto_json["carrito"]
    for _ in range(2):
        r = chat("mi casa queda detrás del parque", ia='{"entrega": {}}')
        assert "dirección completa" in r[0].texto
        assert "copa queso" not in r[0].texto
    assert _conv(db).modo is ModoConversacion.BOT
    assert _conv(db).contexto_json["carrito"] == carrito
    assert _conv(db).contexto_json["entrega"]["medio_pago"] == "efectivo"
    assert db.scalars(select(Pedido)).all() == []


def test_recoger_descarta_direccion_sin_confirmar(db, chat):
    _hasta_resumen(chat)
    chat(boton="confirmar")
    chat(boton="pago:efectivo")
    chat("CRA 40 96a02")
    chat(boton="entrega:recoger")
    pedido = db.scalars(select(Pedido)).one()
    assert pedido.tipo_entrega is TipoEntrega.RECOGER
    assert pedido.direccion is None
    assert "direccion_por_confirmar" not in _conv(db).contexto_json
