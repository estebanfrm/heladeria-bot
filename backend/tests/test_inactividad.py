"""Cierre, reapertura y temporizador con PostgreSQL y HTTP de WhatsApp sustituido."""

import asyncio
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import sessionmaker

from app import ciclo_de_vida
from app.canales.whatsapp_api import ErrorWhatsApp
from app.config import settings
from app.conversacion.inactividad import cerrar_si_inactiva
from app.conversacion.motor import Entrada, Motor
from app.dependencias import get_enviador_whatsapp, get_proveedor, get_sesiones
from app.enums import Canal, EstadoPedido, ModoConversacion
from app.enums import EstadoConversacion as E
from app.ia.interpretacion import Interpretacion
from app.ia.proveedores import ProveedorFalso
from app.menu.carga import aplicar_menu
from app.models import Conversacion, Mensaje, Pedido
from app.whatsapp_demo import app


@pytest.fixture
def hilo(db, menu_demo, monkeypatch):
    aplicar_menu(db, menu_demo)
    monkeypatch.setattr(settings, "chat_inactivity_minutes", 30)
    motor = Motor(db, ProveedorFalso([]))
    motor.procesar(Entrada(canal=Canal.WHATSAPP, id_externo="573000000000", boton="pedir"))
    conv = db.scalars(select(Conversacion)).one()
    conv.estado = E.DATOS_ENTREGA
    conv.contexto_json = {
        "carrito": [{"producto": "granizado_lulo", "cantidad": 1}],
        "entrega": {"medio_pago": "efectivo"},
        "direccion_por_confirmar": "CRA 40 96a02",
    }
    db.flush()
    return motor, conv


def envejecer(db, conv, momento):
    conv.creado = momento
    conv.actualizado = momento
    db.execute(update(Mensaje).where(Mensaje.conversacion_id == conv.id).values(creado=momento))
    db.flush()


def decir(motor, texto="", boton=None):
    return motor.procesar(
        Entrada(canal=Canal.WHATSAPP, id_externo="573000000000", texto=texto, boton=boton)
    )


def test_cierre_a_los_30_minutos_conserva_historial_y_vacia_borrador(db, hilo):
    _, conv = hilo
    ahora = datetime.now(UTC)
    envejecer(db, conv, ahora - timedelta(minutes=30))
    total = db.scalar(select(func.count(Mensaje.id)))
    assert not cerrar_si_inactiva(db, conv, ahora=ahora - timedelta(microseconds=1))
    assert cerrar_si_inactiva(db, conv, ahora=ahora)
    assert conv.estado is E.CANCELADA
    assert "carrito" not in conv.contexto_json
    assert "entrega" not in conv.contexto_json
    assert "direccion_por_confirmar" not in conv.contexto_json
    assert db.scalar(select(func.count(Mensaje.id))) == total + 1
    assert not cerrar_si_inactiva(db, conv, ahora=ahora + timedelta(hours=1))
    assert db.scalar(select(func.count(Mensaje.id))) == total + 1


def test_respuesta_reciente_reinicia_el_plazo(db, hilo):
    motor, conv = hilo
    ahora = datetime.now(UTC)
    envejecer(db, conv, ahora - timedelta(minutes=29))
    decir(motor, "CRA 40 96a02")
    assert not cerrar_si_inactiva(db, conv, ahora=ahora + timedelta(minutes=2))
    assert conv.estado is E.DATOS_ENTREGA
    assert conv.contexto_json["direccion_por_confirmar"] == "CRA 40 96a02"


@pytest.mark.parametrize(
    "entrada",
    [
        {"texto": "hola"},
        {"boton": "direccion:confirmar"},
        {"boton": "pago:efectivo"},
    ],
)
def test_vencimiento_al_recibir_mensaje_ignora_datos_y_botones_viejos(db, hilo, entrada):
    motor, conv = hilo
    envejecer(db, conv, datetime.now(UTC) - timedelta(minutes=31))
    r = decir(motor, **entrada)
    assert conv.estado is E.CANCELADA
    assert r[0].botones[0].id == "chat:nuevo"
    assert db.scalars(select(Pedido)).all() == []
    assert motor.proveedor.llamadas == []
    assert conv.contexto_json["aviso_cierre_pendiente"] is False


@pytest.mark.parametrize("entrada", [{"texto": "nuevo chat"}, {"boton": "chat:nuevo"}])
def test_reabrir_es_decision_del_usuario_y_no_recupera_el_pedido_viejo(db, hilo, entrada):
    motor, conv = hilo
    conv.modo = ModoConversacion.HUMANO
    envejecer(db, conv, datetime.now(UTC) - timedelta(minutes=31))
    r = decir(motor, **entrada)
    assert r[0].texto.startswith("¡Hola!")
    assert conv.estado is E.SALUDO
    assert conv.modo is ModoConversacion.BOT
    assert "sesion_iniciada_en" in conv.contexto_json
    assert "carrito" not in conv.contexto_json
    assert motor.proveedor.llamadas == []
    motor.proveedor.respuestas.append(
        Interpretacion(
            intencion="pedido",
            items=[{"producto": "cono_1", "cantidad": 1}],
        ).model_dump_json()
    )
    r = decir(motor, "un cono")
    assert "Cono" in r[0].texto
    assert "Granizado" not in r[0].texto


def test_boton_de_otro_cierre_no_vacia_un_chat_nuevo(db, hilo):
    motor, conv = hilo
    antes = dict(conv.contexto_json)
    decir(motor, boton="chat:nuevo")
    assert conv.estado is E.DATOS_ENTREGA
    assert conv.contexto_json == antes


@pytest.mark.parametrize("repetir_boton", [False, True])
def test_nuevo_chat_por_webhook_envia_saludo_y_permite_repetir_boton(
    db, hilo, monkeypatch, repetir_boton
):
    motor, conv = hilo
    envejecer(db, conv, datetime.now(UTC) - timedelta(minutes=31))
    cerrar_si_inactiva(db, conv)
    db.commit()
    sesiones = sessionmaker(bind=db.bind, join_transaction_mode="create_savepoint")
    enviador = EnviadorPrueba()
    monkeypatch.setattr(settings, "wa_app_secret", "secreto-prueba")
    app.dependency_overrides[get_sesiones] = lambda: sesiones
    app.dependency_overrides[get_proveedor] = lambda: motor.proveedor
    app.dependency_overrides[get_enviador_whatsapp] = lambda: enviador
    try:
        with TestClient(app) as cliente:
            for numero in range(2 if repetir_boton else 1):
                cuerpo = json.dumps(
                    {
                        "entry": [
                            {
                                "changes": [
                                    {
                                        "value": {
                                            "messages": [
                                                {
                                                    "from": conv.id_externo,
                                                    "id": f"wamid.nuevo-chat-prueba-{numero}",
                                                    "type": "interactive",
                                                    "interactive": {
                                                        "button_reply": {
                                                            "id": "chat:nuevo",
                                                            "title": "Nuevo chat",
                                                        }
                                                    },
                                                }
                                            ]
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ).encode()
                firma = "sha256=" + hmac.new(b"secreto-prueba", cuerpo, hashlib.sha256).hexdigest()
                respuesta = cliente.post(
                    "/webhook/whatsapp",
                    content=cuerpo,
                    headers={"X-Hub-Signature-256": firma, "Content-Type": "application/json"},
                )
                assert respuesta.status_code == 200
                assert respuesta.json() == {"recibidos": 1}
        db.refresh(conv)
        assert conv.estado is E.SALUDO and conv.modo is ModoConversacion.BOT
        assert "carrito" not in conv.contexto_json
        assert len(enviador.envios) == (2 if repetir_boton else 1)
        assert all(r.texto.startswith("¡Hola!") for _, r in enviador.envios)
        assert {b.id for b in enviador.envios[-1][1].botones} == {"menu", "pedir", "humano"}
        assert motor.proveedor.llamadas == []
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("estado", [E.ESPERANDO_PAGO, E.PEDIDO_CONFIRMADO])
def test_pedido_registrado_no_se_cancela_por_cerrar_chat(db, hilo, estado):
    motor, conv = hilo
    conv.contexto_json.pop("direccion_por_confirmar")
    decir(motor, "Cra 8 #80-70")
    pedido = db.scalars(select(Pedido)).one()
    pedido.estado = (
        EstadoPedido.PENDIENTE_PAGO if estado is E.ESPERANDO_PAGO else EstadoPedido.EN_PREPARACION
    )
    conv.estado = estado
    envejecer(db, conv, datetime.now(UTC) - timedelta(minutes=31))
    resultado = cerrar_si_inactiva(db, conv)
    assert resultado is (estado is E.PEDIDO_CONFIRMADO)
    assert pedido.estado is (
        EstadoPedido.PENDIENTE_PAGO if estado is E.ESPERANDO_PAGO else EstadoPedido.EN_PREPARACION
    )
    assert pedido.total == 8000


class EnviadorPrueba:
    def __init__(self, fallar=False):
        self.envios = []
        self.fallar = fallar

    def enviar(self, telefono, respuesta):
        if self.fallar:
            raise ErrorWhatsApp("Fallo simulado")
        self.envios.append((telefono, respuesta))


def test_temporizador_cierra_sin_otro_mensaje_y_no_duplica_aviso(db, hilo):
    _, conv = hilo
    ahora = datetime.now(UTC)
    envejecer(db, conv, ahora - timedelta(minutes=31))
    db.commit()
    sesiones = sessionmaker(bind=db.bind, join_transaction_mode="create_savepoint")
    enviador = EnviadorPrueba()
    assert ciclo_de_vida.procesar_cierres(sesiones, enviador, ahora=ahora) == {
        "cerradas": 1,
        "avisos": 1,
    }
    assert ciclo_de_vida.procesar_cierres(sesiones, enviador, ahora=ahora) == {
        "cerradas": 0,
        "avisos": 0,
    }
    assert len(enviador.envios) == 1
    assert enviador.envios[0][1].botones[0].id == "chat:nuevo"
    db.refresh(conv)
    assert conv.estado is E.CANCELADA
    assert conv.contexto_json["aviso_cierre_pendiente"] is False


def test_fallo_de_envio_conserva_cierre_y_reintenta_aviso(db, hilo):
    _, conv = hilo
    ahora = datetime.now(UTC)
    envejecer(db, conv, ahora - timedelta(minutes=31))
    db.commit()
    sesiones = sessionmaker(bind=db.bind, join_transaction_mode="create_savepoint")
    enviador = EnviadorPrueba(fallar=True)
    assert ciclo_de_vida.procesar_cierres(sesiones, enviador, ahora=ahora) == {
        "cerradas": 1,
        "avisos": 0,
    }
    db.refresh(conv)
    assert conv.estado is E.CANCELADA
    assert conv.contexto_json["aviso_cierre_pendiente"] is True
    enviador.fallar = False
    assert ciclo_de_vida.procesar_cierres(sesiones, enviador, ahora=ahora) == {
        "cerradas": 0,
        "avisos": 1,
    }


def test_reinicio_fuera_de_ventana_whatsapp_cierra_sin_enviar(db, hilo):
    _, conv = hilo
    ahora = datetime.now(UTC)
    envejecer(db, conv, ahora - timedelta(days=2))
    db.commit()
    sesiones = sessionmaker(bind=db.bind, join_transaction_mode="create_savepoint")
    enviador = EnviadorPrueba()
    assert ciclo_de_vida.procesar_cierres(sesiones, enviador, ahora=ahora) == {
        "cerradas": 1,
        "avisos": 0,
    }
    assert enviador.envios == []


def test_temporizador_en_ambas_apps_y_apagado_limpio(monkeypatch):
    from app.main import app as app_principal

    eventos = []

    async def vigilar(detener):
        eventos.append("inicio")
        await detener.wait()
        eventos.append("fin")

    monkeypatch.setattr(settings, "chat_inactivity_worker_enabled", True)
    monkeypatch.setattr(ciclo_de_vida, "vigilar_inactividad", vigilar)
    for aplicacion in (app, app_principal):
        with TestClient(aplicacion):
            pass
    assert eventos == ["inicio", "fin", "inicio", "fin"]


def test_temporizador_sigue_despues_de_un_error(monkeypatch):
    llamadas = []
    detener = asyncio.Event()
    loop = None

    def ciclo(*_args):
        llamadas.append(1)
        if len(llamadas) == 1:
            raise RuntimeError("BD temporalmente no disponible")
        loop.call_soon_threadsafe(detener.set)

    async def ejecutar():
        nonlocal loop
        loop = asyncio.get_running_loop()
        await ciclo_de_vida.vigilar_inactividad(detener)

    monkeypatch.setattr(settings, "chat_inactivity_poll_seconds", 0.001)
    monkeypatch.setattr(ciclo_de_vida, "procesar_cierres", ciclo)
    monkeypatch.setattr(ciclo_de_vida, "get_sesiones", lambda: None)
    monkeypatch.setattr(ciclo_de_vida, "get_enviador_whatsapp", lambda: None)
    asyncio.run(ejecutar())
    assert len(llamadas) == 2
