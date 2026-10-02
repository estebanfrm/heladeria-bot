"""Carga del seed a la BD (paso 2 de la Fase 1) y lectura del menú vigente."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app
from app.menu import carga
from app.menu.carga import MenuNoCargado, aplicar_menu, hay_version_nueva, leer_menu
from app.models import MedioPago, Opcion, Producto
from tests.conftest import SEED_DEMO


def _conteos(db) -> dict[str, int]:
    return {
        nombre: db.scalar(select(func.count()).select_from(tabla))
        for nombre, tabla in Base.metadata.tables.items()
    }


def test_seed_a_bd_y_de_vuelta_es_identico(db, menu_demo):
    aplicar_menu(db, menu_demo)
    db.expire_all()

    assert leer_menu(db).model_dump() == menu_demo.model_dump()


def test_aplicar_dos_veces_no_duplica(db, menu_demo):
    aplicar_menu(db, menu_demo)
    antes = _conteos(db)
    aplicar_menu(db, menu_demo)

    assert _conteos(db) == antes
    assert antes["producto"] == 26
    assert antes["opcion"] == sum(len(g.opciones) for g in menu_demo.grupos_opciones)


def test_cambios_del_seed_se_aplican_sin_borrar(db, menu_demo):
    aplicar_menu(db, menu_demo)

    nuevo = menu_demo.model_copy(deep=True)
    nuevo.version = 2
    nuevo.producto("copa_queso").precio = 13000
    nuevo.productos = [p for p in nuevo.productos if p.id != "granizado_cafe"]
    salsas = nuevo.grupo("salsas_generales")
    salsas.opciones = [o for o in salsas.opciones if o.id != "mora"]
    nuevo.producto("banana_split").selecciones.pop()  # quita el topping
    nuevo.medios_pago = [m for m in nuevo.medios_pago if m.id != "datafono"]
    aplicar_menu(db, nuevo)
    db.expire_all()

    assert leer_menu(db).model_dump() == nuevo.model_dump()
    # Lo retirado sigue en la BD (pedidos viejos lo referencian), pero inactivo
    cafe = db.scalar(select(Producto).where(Producto.codigo == "granizado_cafe"))
    assert cafe is not None and not cafe.activo
    mora = db.scalar(select(Opcion).where(Opcion.codigo == "mora"))
    assert mora is not None and not mora.activo
    datafono = db.scalar(select(MedioPago).where(MedioPago.codigo == "datafono"))
    assert datafono is not None and not datafono.activo


def test_hay_version_nueva(db, menu_demo):
    assert hay_version_nueva(db, menu_demo)  # BD vacía
    aplicar_menu(db, menu_demo)
    assert not hay_version_nueva(db, menu_demo)
    menu_demo.version += 1
    assert hay_version_nueva(db, menu_demo)


def test_leer_sin_menu_cargado_falla(db):
    with pytest.raises(MenuNoCargado):
        leer_menu(db)


def test_cli_auto_solo_aplica_con_version_nueva(db, monkeypatch, capsys):
    monkeypatch.setattr(carga.settings, "seed_file", SEED_DEMO)
    monkeypatch.setattr(
        carga,
        "SessionLocal",
        sessionmaker(bind=db.connection(), join_transaction_mode="create_savepoint"),
    )

    carga.main(["--auto"])
    assert "aplicado: 26 productos" in capsys.readouterr().out

    carga.main(["--auto"])
    assert "ya aplicado" in capsys.readouterr().out


@pytest.fixture
def cliente_http(db):
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_endpoint_menu_lee_de_la_bd(db, menu_demo, cliente_http):
    assert cliente_http.get("/menu").status_code == 503  # aún sin cargar

    aplicar_menu(db, menu_demo)
    respuesta = cliente_http.get("/menu")

    assert respuesta.status_code == 200
    assert respuesta.json() == menu_demo.model_dump(mode="json")
