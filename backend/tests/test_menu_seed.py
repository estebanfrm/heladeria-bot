from pathlib import Path

import pytest

from app.menu.schema import Menu, cargar_menu

SEED_DEMO = Path(__file__).resolve().parents[2] / "seeds" / "demo.json"


@pytest.fixture(scope="module")
def menu() -> Menu:
    return cargar_menu(SEED_DEMO)


def test_seed_demo_es_valido(menu):
    assert menu.negocio.nombre == "Heladería Demo"
    assert len(menu.productos) > 0


def test_once_sabores(menu):
    assert len(menu.grupo("sabores").opciones) == 11


def test_reglas_del_chat_real(menu):
    """Pedido real del 28/09/2026: copa queso + banana split = $24.000."""
    copa = menu.producto("copa_queso")
    banana = menu.producto("banana_split")
    assert copa.precio + banana.precio == 24000
    assert {s.grupo: s.cantidad for s in copa.selecciones}["sabores"] == 2
    assert {s.grupo: s.cantidad for s in banana.selecciones}["sabores"] == 3


def test_demo_no_usa_cuentas_reales(menu):
    for m in menu.medios_pago:
        if m.cuenta:
            assert set(m.cuenta.replace(" ", "").replace("-", "")) <= {"0", "3"}


def test_referencia_rota_falla(menu):
    datos = menu.model_dump()
    datos["productos"][0]["categoria"] = "no_existe"
    with pytest.raises(ValueError, match="categoría 'no_existe' no existe"):
        Menu.model_validate(datos)
