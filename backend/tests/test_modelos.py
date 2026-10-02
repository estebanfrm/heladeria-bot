"""El esquema soporta el pedido real del chat (copa queso + banana split = $24.000)."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.enums import Canal, EstadoConversacion, EstadoPedido, TipoGrupo
from app.models import (
    Categoria,
    Cliente,
    Conversacion,
    GrupoOpcion,
    ItemOpcion,
    ItemPedido,
    MedioPago,
    Opcion,
    Pedido,
    Producto,
    ProductoSeleccion,
)


def _grupo(codigo: str, tipo: TipoGrupo, nombre: str, opciones: dict[str, str]) -> GrupoOpcion:
    return GrupoOpcion(
        codigo=codigo,
        tipo=tipo,
        nombre=nombre,
        opciones=[Opcion(codigo=c, nombre=n) for c, n in opciones.items()],
    )


@pytest.fixture
def catalogo(db):
    """Catálogo mínimo para el caso real (la carga completa del seed es el paso 2)."""
    sabores = _grupo(
        "sabores",
        TipoGrupo.SABOR,
        "Sabor de helado",
        {"brownie": "Brownie", "fresa": "Fresa", "vainilla_chips": "Vainilla chips"},
    )
    salsas = _grupo("salsas_generales", TipoGrupo.SALSA, "Salsa", {"frutos_rojos": "Frutos rojos"})
    toppings = _grupo(
        "toppings_base", TipoGrupo.TOPPING, "Topping", {"mani": "Maní", "oreo": "Oreo triturado"}
    )
    especiales = Categoria(codigo="especiales", nombre="Especiales", orden=1)

    def producto(codigo: str, nombre: str, num_sabores: int) -> Producto:
        return Producto(
            codigo=codigo,
            nombre=nombre,
            categoria=especiales,
            precio=12000,
            selecciones=[
                ProductoSeleccion(grupo=sabores, cantidad=num_sabores, orden=0),
                ProductoSeleccion(grupo=salsas, cantidad=1, orden=1),
                ProductoSeleccion(grupo=toppings, cantidad=1, orden=2),
            ],
        )

    nequi = MedioPago(
        codigo="nequi",
        nombre="Nequi",
        numero_cuenta="300 000 0000",
        titular="Heladería Demo",
        requiere_comprobante=True,
    )
    copa = producto("copa_queso", "Copa queso", 2)
    banana = producto("banana_split", "Banana split", 3)
    db.add_all([copa, banana, nequi])
    db.flush()

    opciones = {o.codigo: o for g in (sabores, salsas, toppings) for o in g.opciones}
    return {"copa_queso": copa, "banana_split": banana, "nequi": nequi, **opciones}


@pytest.fixture
def conversacion(db):
    cliente = Cliente(telefono="573000000000", nombre="Cliente Demo")
    conv = Conversacion(cliente=cliente, canal=Canal.WHATSAPP, id_externo="573000000000")
    db.add(conv)
    db.flush()
    return conv


def _item(producto: Producto, elegidas: list[Opcion]) -> ItemPedido:
    return ItemPedido(
        producto=producto,
        nombre=producto.nombre,
        cantidad=1,
        precio_unitario=producto.precio,
        opciones=[
            ItemOpcion(opcion=o, nombre=o.nombre, posicion=i) for i, o in enumerate(elegidas)
        ],
    )


def test_pedido_real_del_chat(db, catalogo, conversacion):
    c = catalogo
    items = [
        _item(c["copa_queso"], [c["brownie"], c["fresa"], c["frutos_rojos"], c["mani"]]),
        _item(
            c["banana_split"],
            [c["brownie"], c["vainilla_chips"], c["brownie"], c["frutos_rojos"], c["oreo"]],
        ),
    ]
    subtotal = sum(i.precio_unitario * i.cantidad for i in items)
    pedido = Pedido(
        cliente=conversacion.cliente,
        conversacion=conversacion,
        items=items,
        subtotal=subtotal,
        domicilio=0,
        total=subtotal,
        direccion="Calle Falsa 123",
        medio_pago=c["nequi"],
    )
    db.add(pedido)
    db.flush()
    db.expire_all()

    guardado = db.get(Pedido, pedido.id)
    assert guardado.total == 24000
    assert guardado.estado is EstadoPedido.BORRADOR
    assert [i.nombre for i in guardado.items] == ["Copa queso", "Banana split"]
    # El sabor repetido se conserva y en el orden elegido
    assert [o.nombre for o in guardado.items[1].opciones] == [
        "Brownie",
        "Vainilla chips",
        "Brownie",
        "Frutos rojos",
        "Oreo triturado",
    ]


def test_total_que_no_cuadra_es_rechazado(db, conversacion):
    db.add(
        Pedido(
            cliente=conversacion.cliente,
            conversacion=conversacion,
            subtotal=24000,
            domicilio=0,
            total=20000,
        )
    )
    with pytest.raises(IntegrityError, match="ck_pedido_total_cuadra"):
        db.flush()


def test_misma_opcion_en_varios_grupos(db):
    """'frutos_rojos' existe como salsa en varios grupos sin chocar."""
    for codigo in ("salsas_base", "salsas_generales"):
        db.add(_grupo(codigo, TipoGrupo.SALSA, "Salsa", {"frutos_rojos": "Frutos rojos"}))
    db.flush()
    assert len(db.scalars(select(Opcion).where(Opcion.codigo == "frutos_rojos")).all()) == 2


def test_enums_como_texto_y_contexto_mutable(db, conversacion):
    conversacion.contexto_json["fallos"] = 1  # cambio in situ: MutableDict lo detecta
    db.flush()
    db.expire_all()

    fila = db.execute(
        text("SELECT canal, estado, modo, contexto_json FROM conversacion WHERE id = :id"),
        {"id": conversacion.id},
    ).one()
    assert fila.canal == "whatsapp"
    assert fila.estado == EstadoConversacion.INICIO.value
    assert fila.modo == "bot"
    assert fila.contexto_json == {"fallos": 1}
