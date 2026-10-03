"""Selecciones de WhatsApp: sin IA, con paginación, menú vigente y botones antiguos."""

import copy
import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.canales.whatsapp import extraer_entradas
from app.canales.whatsapp_api import construir_mensajes
from app.conversacion.inactividad import cerrar_si_inactiva
from app.conversacion.motor import Entrada, Motor
from app.conversacion.seleccion import presentar
from app.enums import Canal, EstadoPedido
from app.enums import EstadoConversacion as E
from app.ia.proveedores import ProveedorFalso
from app.menu.carga import aplicar_menu
from app.models import Conversacion, Opcion, Pedido
from app.pedidos.carrito import ItemSolicitado, validar_carrito


@pytest.fixture
def formulario(db, menu_demo):
    aplicar_menu(db, menu_demo)
    proveedor = ProveedorFalso([])
    motor = Motor(db, proveedor)

    def enviar(*, items=None, boton=None, texto=None):
        if items is not None:
            proveedor.respuestas.append(json.dumps({"intencion": "pedido", "items": items}))
            entrada = Entrada(canal=Canal.WHATSAPP, id_externo="573000000000", texto="mi pedido")
        elif texto is not None:
            entrada = Entrada(canal=Canal.WHATSAPP, id_externo="573000000000", texto=texto)
        else:
            payload = {
                "entry": [
                    {
                        "changes": [
                            {
                                "value": {
                                    "messages": [
                                        {
                                            "from": "573000000000",
                                            "type": "interactive",
                                            "interactive": {
                                                "list_reply": {"id": boton, "title": "Elegir"}
                                            },
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                ]
            }
            entrada = extraer_entradas(payload)[0]
        return motor.procesar(entrada)[0]

    enviar.proveedor = proveedor
    enviar.conv = lambda: db.scalars(select(Conversacion)).one()
    return enviar


def tocar(formulario, respuesta, codigo):
    opciones = [b for b in respuesta.botones if b.id.startswith("seleccion:")]
    if not any(b.id.endswith(":" + codigo) for b in opciones):
        pagina = next(b for b in respuesta.botones if b.titulo == "Más opciones →")
        respuesta = formulario(boton=pagina.id)
    return formulario(
        boton=next(
            b.id
            for b in respuesta.botones
            if b.id.startswith("seleccion:") and b.id.endswith(":" + codigo)
        )
    )


@pytest.mark.parametrize(
    "codigo",
    [
        "vainilla_chips",
        "vainilla",
        "brownie",
        "barrilete",
        "maracuya",
        "mandarina_limon",
        "fresa",
        "lulo",
        "yogurt_frutos_rojos",
        "chocolate",
        "ron_con_pasas",
    ],
)
def test_todos_los_sabores_son_accesibles_y_caben_en_la_lista(menu_demo, codigo):
    resultado = validar_carrito(menu_demo, [ItemSolicitado(producto="copa_queso")])
    respuestas = [presentar(menu_demo, resultado, "token", pagina) for pagina in range(2)]
    assert any(b.id == "seleccion:token:" + codigo for r in respuestas for b in r.botones)
    for r in respuestas:
        assert "salsa" not in r.texto.lower() and "topping" not in r.texto.lower()
        assert len(r.texto) <= 1024
        mensaje = construir_mensajes("destinatario", r)[0]["interactive"]
        assert mensaje["type"] == "list"
        filas = mensaje["action"]["sections"][0]["rows"]
        assert len(filas) <= 10
        assert all(len(f["title"]) <= 24 and len(f["id"]) <= 200 for f in filas)


def test_copa_completa_por_listas_repite_sabor_solo_con_otra_eleccion(db, formulario):
    r = formulario(items=[{"producto": "copa_queso", "cantidad": 2}])
    boton_viejo = next(b.id for b in r.botones if b.id.endswith(":vainilla"))
    r = tocar(formulario, r, "vainilla")
    assert "2 de 2" in r.texto and "vainilla" in r.texto
    antes = copy.deepcopy(formulario.conv().contexto_json)
    r = formulario(boton=boton_viejo)
    assert formulario.conv().contexto_json == antes
    assert "2 de 2" in r.texto  # el botón anterior no cuenta como segundo sabor
    r = tocar(formulario, r, "vainilla")
    assert "Elige salsa: 1 de 1" in r.texto
    r = tocar(formulario, r, "frutos_rojos")
    assert "Elige topping: 1 de 1" in r.texto
    r = tocar(formulario, r, "oreo")
    assert formulario.conv().estado is E.RESUMEN and "$24.000" in r.texto
    assert len(formulario.proveedor.llamadas) == 1
    assert not db.scalars(select(Pedido)).all()
    formulario(boton="confirmar")
    formulario(texto="recoger en el local")
    formulario(boton="pago:efectivo")
    assert db.scalars(select(Pedido)).one().total == 24000


def test_paginacion_no_modifica_carrito_y_reiniciar_invalida_listas(db, formulario):
    r = formulario(items=[{"producto": "copa_queso"}])
    inicial = copy.deepcopy(formulario.conv().contexto_json)
    r = formulario(boton=next(b.id for b in r.botones if b.titulo == "Más opciones →"))
    assert "Página 2 de 2" in r.texto and formulario.conv().contexto_json == inicial
    r = formulario(boton=next(b.id for b in r.botones if b.titulo == "← Anteriores"))
    viejo = next(b.id for b in r.botones if b.id.endswith(":vainilla"))
    r = tocar(formulario, r, "vainilla")
    r = formulario(boton=next(b.id for b in r.botones if b.titulo == "Elegir de nuevo"))
    antes = copy.deepcopy(formulario.conv().contexto_json)
    assert antes["carrito"][0]["opciones"] == {} and "1 de 2" in r.texto
    formulario(boton=viejo)
    assert formulario.conv().contexto_json == antes
    assert not db.scalars(select(Pedido)).all()


@pytest.mark.parametrize("codigo", ["frutos_rojos", "sabor_inventado", "vainilla:precio:0"])
def test_seleccion_falsificada_no_acepta_salsas_como_sabores(db, formulario, codigo):
    formulario(items=[{"producto": "copa_queso"}])
    antes = copy.deepcopy(formulario.conv().contexto_json)
    token = antes["opciones_token"]
    formulario(boton=f"seleccion:{token}:{codigo}")
    assert formulario.conv().contexto_json == antes
    assert len(formulario.proveedor.llamadas) == 1
    assert not db.scalars(select(Pedido)).all()


def test_opcion_agotada_despues_de_mostrar_lista_se_rechaza(db, formulario):
    r = formulario(items=[{"producto": "copa_queso"}])
    boton = next(b.id for b in r.botones if b.id.endswith(":brownie"))
    opcion = db.scalars(select(Opcion).where(Opcion.codigo == "brownie")).one()
    opcion.disponible = False
    db.flush()
    antes = copy.deepcopy(formulario.conv().contexto_json)
    r = formulario(boton=boton)
    assert formulario.conv().contexto_json == antes
    assert all(not b.id.endswith(":brownie") for b in r.botones)


def test_varios_productos_y_topping_adicional_seleccionados_sin_ia(db, formulario):
    copa = {
        "producto": "copa_queso",
        "opciones": {
            "sabor": ["vainilla", "fresa"],
            "salsa": ["frutos_rojos"],
            "topping": ["oreo"],
        },
        "adicionales": [{"adicional": "topping_extra"}],
    }
    r = formulario(items=[copa, {"producto": "cono_1"}])
    assert "topping adicional" in r.texto.lower()
    r = tocar(formulario, r, "mani")
    assert "Cono" in r.texto
    r = tocar(formulario, r, "lulo")
    assert formulario.conv().estado is E.RESUMEN
    assert len(formulario.proveedor.llamadas) == 1 and not db.scalars(select(Pedido)).all()


def test_lista_de_chat_cerrado_no_actua_en_nuevo_chat(db, formulario):
    r = formulario(items=[{"producto": "copa_queso"}])
    viejo = next(b.id for b in r.botones if b.id.endswith(":vainilla"))
    conv = formulario.conv()
    fecha = datetime.now(UTC) - timedelta(minutes=31)
    conv.creado = conv.actualizado = fecha
    for mensaje in conv.mensajes:
        mensaje.creado = fecha
    db.flush()
    assert cerrar_si_inactiva(db, conv)
    formulario(boton="chat:nuevo")
    formulario(items=[{"producto": "copa_queso"}])
    antes = copy.deepcopy(conv.contexto_json)
    formulario(boton=viejo)
    assert conv.contexto_json == antes and conv.estado is E.COMPLETANDO_OPCIONES


def test_no_ofrece_repetir_sabores_cuando_el_menu_lo_prohibe(menu_demo):
    menu_demo.producto("copa_queso").selecciones[0].permite_repetir = False
    resultado = validar_carrito(
        menu_demo, [ItemSolicitado(producto="copa_queso", opciones={"sabor": ["vainilla"]})]
    )
    r = presentar(menu_demo, resultado, "token")
    assert all(not b.id.endswith(":vainilla") for b in r.botones)
    assert any(b.id.endswith(":brownie") for b in r.botones)


@pytest.mark.parametrize("medio", ["nequi", "efectivo"])
def test_lista_del_resumen_no_cambia_pedido_registrado(db, formulario, medio):
    opciones = {"sabor": ["vainilla", "fresa"], "salsa": ["frutos_rojos"], "topping": ["oreo"]}
    r = formulario(items=[{"producto": "copa_queso", "opciones": opciones}])
    viejo = next(b.id for b in r.botones if b.titulo == "Elegir de nuevo")
    formulario(boton="confirmar")
    formulario(texto="recoger en el local")
    formulario(boton="pago:" + medio)
    antes = copy.deepcopy(formulario.conv().contexto_json)
    formulario(boton=viejo)
    pedido = db.scalars(select(Pedido)).one()
    assert pedido.total == 12000 and formulario.conv().contexto_json == antes


def test_pago_verificado_durante_edicion_bloquea_seleccion(db, formulario):
    formulario(items=[{"producto": "granizado_lulo"}])
    formulario(boton="confirmar")
    formulario(texto="recoger en el local")
    formulario(boton="pago:efectivo")
    formulario(boton="cambiar")
    r = formulario(items=[{"producto": "copa_queso"}])
    boton = next(b.id for b in r.botones if b.id.endswith(":vainilla"))
    pedido = db.scalars(select(Pedido)).one()
    pedido.estado = EstadoPedido.PAGO_VERIFICADO
    antes = copy.deepcopy(formulario.conv().contexto_json)
    r = formulario(boton=boton)
    assert "no puedo cambiarlo" in r.texto
    assert formulario.conv().contexto_json == antes and pedido.total == 8000
