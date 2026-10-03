"""Carrito y reglas (paso 3 de la Fase 1), con los mensajes del chat real del 28/09/2026."""

import pytest
from pydantic import ValidationError

from app.enums import TipoEntrega
from app.menu.schema import Opcion
from app.pedidos.carrito import (
    AdicionalSolicitado,
    ItemSolicitado,
    normalizar_opciones,
    validar_carrito,
    validar_item,
)

# "Una copa queso, con brownie… y fresa" + "brownie, vainilla chips, brownie · frutos rojos · oreo"
COPA_QUESO = ItemSolicitado(
    producto="copa_queso",
    opciones={"sabor": ["brownie", "fresa"], "salsa": ["frutos_rojos"], "topping": ["mani"]},
)
BANANA_SPLIT = ItemSolicitado(
    producto="banana_split",
    opciones={
        "sabor": ["brownie", "vainilla_chips", "brownie"],
        "salsa": ["frutos_rojos"],
        "topping": ["oreo"],
    },
)


@pytest.mark.parametrize(
    ("opciones", "esperadas"),
    [
        (
            {"sabor": ["vainilla", "frutos_rojos"], "topping": ["oreo"]},
            {"sabor": ["vainilla"], "salsa": ["frutos_rojos"], "topping": ["oreo"]},
        ),
        (
            {"sabor": ["vainilla", "frutos_rojos"], "salsa": ["frutos_rojos"]},
            {"sabor": ["vainilla"], "salsa": ["frutos_rojos"]},
        ),
        (
            {"sabor": ["oreo"], "topping": ["vainilla", "vainilla"]},
            {"sabor": ["vainilla", "vainilla"], "topping": ["oreo"]},
        ),
    ],
)
def test_reubica_solo_codigos_exactos_sin_duplicarlos_ni_mutar_el_original(
    menu_demo, opciones, esperadas
):
    original = ItemSolicitado(producto="copa_queso", cantidad=3, opciones=opciones)
    corregido = normalizar_opciones(menu_demo, original)
    assert corregido.opciones == esperadas
    assert corregido.cantidad == 3 and original.opciones == opciones
    assert normalizar_opciones(menu_demo, corregido) == corregido


@pytest.mark.parametrize(
    ("producto", "opciones"),
    [
        ("copa_queso", {"variante": ["maracuya"]}),  # válido en dos grupos: ambiguo
        ("copa_queso", {"sabor": ["sabor_inventado"]}),
        ("copa_queso", {"salsa": ["mora"]}),  # existe en otro producto, no en la copa
        ("granizado_lulo", {"topping": ["oreo"]}),
        ("pizza", {"sabor": ["frutos_rojos"]}),
    ],
)
def test_no_reubica_opciones_ambiguas_desconocidas_o_de_otros_productos(
    menu_demo, producto, opciones
):
    original = ItemSolicitado(producto=producto, opciones=opciones)
    assert normalizar_opciones(menu_demo, original) == original
    assert validar_item(menu_demo, original).problemas


def test_reubicar_no_oculta_agotados_excesos_ni_adicionales_invalidos(menu_demo):
    next(
        o for o in menu_demo.grupo("salsas_base").opciones if o.id == "frutos_rojos"
    ).disponible = False
    original = ItemSolicitado(
        producto="copa_queso",
        opciones={"sabor": ["vainilla", "frutos_rojos"]},
        adicionales=[AdicionalSolicitado(adicional="topping_extra", opcion="frutos_rojos")],
    )
    corregido = normalizar_opciones(menu_demo, original)
    validado = validar_item(menu_demo, corregido)
    assert _codigos(validado.problemas) == ["opcion_agotada", "opcion_no_existe"]
    assert corregido.adicionales == original.adicionales
    exceso = normalizar_opciones(
        menu_demo,
        ItemSolicitado(producto="copa_queso", opciones={"sabor": ["frutos_rojos", "frutos_rojos"]}),
    )
    assert exceso.opciones["salsa"] == ["frutos_rojos", "frutos_rojos"]
    next(
        o for o in menu_demo.grupo("salsas_base").opciones if o.id == "frutos_rojos"
    ).disponible = True
    assert "sobran_opciones" in _codigos(validar_item(menu_demo, exceso).problemas)


@pytest.mark.parametrize("modificacion", ["ambigua", "agotada"])
def test_no_sugiere_mezcla_si_ingrediente_es_ambiguo_o_mezcla_agotada(menu_demo, modificacion):
    grupo = menu_demo.grupo("sabores_michelada")
    if modificacion == "agotada":
        next(o for o in grupo.opciones if o.id == "frutos_amarillos").disponible = False
    else:
        grupo.opciones.append(Opcion(id="otra_mezcla", nombre="Otra mezcla (maracuyá y fresa)"))
    resultado = validar_carrito(
        menu_demo, [ItemSolicitado(producto="michelada_soda", opciones={"variante": ["maracuya"]})]
    )
    assert not resultado.completo
    assert all(p.opcion_sugerida is None for p in resultado.items[0].problemas)


def _codigos(problemas) -> list[str]:
    return [p.codigo for p in problemas]


def test_pedido_real_completo_cuesta_24000(menu_demo):
    resultado = validar_carrito(menu_demo, [COPA_QUESO, BANANA_SPLIT])

    assert resultado.completo
    assert resultado.subtotal == 24000
    assert resultado.total == 24000
    banana = resultado.items[1]
    assert [o.nombre for o in banana.opciones] == [
        "Brownie",
        "Vainilla chips",
        "Brownie",
        "Frutos rojos",
        "Oreo triturado",
    ]


def test_primer_mensaje_real_pide_todo_lo_que_falta(menu_demo):
    """'Una copa queso con brownie y fresa. Y un banana split' → faltan salsa/topping y sabores."""
    copa = ItemSolicitado(producto="copa_queso", opciones={"sabor": ["brownie", "fresa"]})
    banana = ItemSolicitado(producto="banana_split")

    resultado = validar_carrito(menu_demo, [copa, banana])

    assert not resultado.completo
    assert resultado.subtotal == 24000  # el precio no depende de las opciones
    faltan_copa = {f.nombre: f.cantidad for f in resultado.items[0].faltantes}
    faltan_banana = {f.nombre: f.cantidad for f in resultado.items[1].faltantes}
    assert faltan_copa == {"Salsa": 1, "Topping": 1}
    assert faltan_banana == {"Sabor de helado": 3, "Salsa": 1, "Topping": 1}
    # Cada producto ofrece su propia lista: copa queso usa salsas_base
    salsas_copa = resultado.items[0].faltantes[0]
    assert [o.nombre for o in salsas_copa.opciones] == ["Frutos rojos", "Maracuyá", "Lecherita"]


def test_faltan_solo_los_sabores_que_no_dijo(menu_demo):
    item = validar_item(
        menu_demo, ItemSolicitado(producto="banana_split", opciones={"sabor": ["brownie"]})
    )

    sabores = next(f for f in item.faltantes if f.grupo == "sabores")
    assert sabores.cantidad == 2


def test_opcion_que_no_es_del_producto(menu_demo):
    """Mora existe como salsa general, pero no en la lista de la copa queso."""
    item = validar_item(
        menu_demo,
        COPA_QUESO.model_copy(update={"opciones": {**COPA_QUESO.opciones, "salsa": ["mora"]}}),
    )

    assert _codigos(item.problemas) == ["opcion_no_existe"]
    assert [f.nombre for f in item.faltantes] == ["Salsa"]  # se vuelve a preguntar
    assert not item.completo


def test_opcion_agotada(menu_demo):
    next(o for o in menu_demo.grupo("sabores").opciones if o.id == "brownie").disponible = False

    item = validar_item(menu_demo, COPA_QUESO)

    assert _codigos(item.problemas) == ["opcion_agotada"]
    assert item.problemas[0].mensaje == "Brownie no está disponible hoy."
    faltante = next(f for f in item.faltantes if f.grupo == "sabores")
    assert "brownie" not in [o.id for o in faltante.opciones]


def test_sobran_opciones(menu_demo):
    item = validar_item(
        menu_demo,
        COPA_QUESO.model_copy(
            update={"opciones": {**COPA_QUESO.opciones, "sabor": ["brownie", "fresa", "lulo"]}}
        ),
    )

    assert _codigos(item.problemas) == ["sobran_opciones"]
    assert item.problemas[0].mensaje == "Copa queso lleva 2 de sabor de helado y elegiste 3."


def test_repetir_cuando_no_se_permite(menu_demo):
    menu_demo.producto("banana_split").selecciones[0].permite_repetir = False

    item = validar_item(menu_demo, BANANA_SPLIT)

    assert _codigos(item.problemas) == ["opcion_repetida"]


def test_tipo_que_el_producto_no_lleva(menu_demo):
    item = validar_item(
        menu_demo, ItemSolicitado(producto="granizado_cafe", opciones={"salsa": ["mora"]})
    )

    assert _codigos(item.problemas) == ["no_aplica"]
    assert item.problemas[0].mensaje == "Granizado de café no lleva salsa."


def test_producto_inexistente_o_inactivo(menu_demo):
    menu_demo.producto("copa_acida").activo = False

    for codigo in ("pizza", "copa_acida"):
        item = validar_item(menu_demo, ItemSolicitado(producto=codigo))
        assert _codigos(item.problemas) == ["producto_no_existe"]
        assert item.total == 0


def test_producto_sin_opciones_queda_completo(menu_demo):
    item = validar_item(menu_demo, ItemSolicitado(producto="granizado_lulo", cantidad=2))

    assert item.completo
    assert item.total == 16000


def test_adicionales_suman_por_unidad(menu_demo):
    copa = COPA_QUESO.model_copy(
        update={
            "cantidad": 2,
            "adicionales": [
                AdicionalSolicitado(adicional="topping_extra", opcion="oreo"),
                AdicionalSolicitado(adicional="chantilly_extra"),
            ],
        }
    )

    item = validar_item(menu_demo, copa)

    assert item.completo
    assert item.total == (12000 + 1700 + 3000) * 2
    assert item.adicionales[0].opcion.nombre == "Oreo triturado"


def test_adicional_que_exige_elegir(menu_demo):
    copa = COPA_QUESO.model_copy(
        update={"adicionales": [AdicionalSolicitado(adicional="topping_extra")]}
    )

    item = validar_item(menu_demo, copa)

    assert not item.completo
    faltante = item.faltantes[0]
    assert faltante.adicional == "topping_extra"
    assert faltante.grupo == "toppings_waffle"
    assert item.total == 12000 + 1700  # el precio ya se conoce


@pytest.mark.parametrize(
    ("adicional", "codigo"),
    [
        (
            AdicionalSolicitado(adicional="topping_extra", opcion="lluvia_colores"),
            "opcion_no_existe",
        ),
        (AdicionalSolicitado(adicional="chantilly_extra", opcion="oreo"), "no_aplica"),
        (AdicionalSolicitado(adicional="mermelada_extra"), "adicional_no_existe"),
    ],
)
def test_adicionales_invalidos(menu_demo, adicional, codigo):
    item = validar_item(menu_demo, COPA_QUESO.model_copy(update={"adicionales": [adicional]}))

    assert _codigos(item.problemas) == [codigo]
    assert item.adicionales == []
    assert item.total == 12000


def test_domicilio_solo_si_es_a_domicilio(menu_demo):
    menu_demo.negocio.domicilio.costo = 3000
    items = [COPA_QUESO, BANANA_SPLIT]

    assert validar_carrito(menu_demo, items).total == 24000  # aún sin elegir entrega
    assert validar_carrito(menu_demo, items, TipoEntrega.RECOGER).total == 24000
    a_domicilio = validar_carrito(menu_demo, items, TipoEntrega.DOMICILIO)
    assert (a_domicilio.subtotal, a_domicilio.domicilio, a_domicilio.total) == (24000, 3000, 27000)


def test_carrito_vacio_no_esta_completo(menu_demo):
    assert not validar_carrito(menu_demo, []).completo


def test_json_de_la_ia_se_valida_y_no_trae_precios(menu_demo):
    """La IA solo entrega códigos: un precio inventado se ignora y un tipo desconocido falla."""
    item = ItemSolicitado.model_validate(
        {"producto": "copa_queso", "precio": 1, "opciones": {"sabor": ["brownie", "fresa"]}}
    )
    assert validar_item(menu_demo, item).precio_unitario == 12000

    with pytest.raises(ValidationError):
        ItemSolicitado.model_validate({"producto": "copa_queso", "opciones": {"salsita": ["x"]}})
    with pytest.raises(ValidationError):
        ItemSolicitado.model_validate({"producto": "copa_queso", "cantidad": 0})
