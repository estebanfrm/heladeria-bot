"""Carrito: valida lo que pidió el cliente contra el menú y calcula los montos.

"La IA interpreta, el código decide": la IA (o los botones) solo producen `ItemSolicitado`
con códigos del menú, sin precios. Aquí se valida todo y se calculan subtotal, domicilio y
total con los precios del `Menu` (que viene de la BD).
"""

import re

from pydantic import BaseModel, Field, computed_field, field_validator

from app.config import settings
from app.conversacion.protecciones import normalizar
from app.enums import TipoEntrega, TipoGrupo
from app.menu.schema import GrupoOpciones, Menu, Opcion, Producto

# --- Lo que pide el cliente --------------------------------------------------------


class AdicionalSolicitado(BaseModel):
    adicional: str  # código, ej. "topping_extra"
    opcion: str | None = None  # si el adicional exige elegir, ej. "oreo"
    cantidad: int = Field(default=1, ge=1, strict=True)


class ItemSolicitado(BaseModel):
    """Un producto pedido. Campos extra (ej. un "precio" inventado por la IA) se ignoran."""

    producto: str  # código, ej. "copa_queso"
    cantidad: int = Field(default=1, ge=1, strict=True)
    # Por tipo, en el orden dicho; pueden repetirse: {"sabor": ["brownie", "fresa", "brownie"]}
    opciones: dict[TipoGrupo, list[str]] = Field(default_factory=dict)
    adicionales: list[AdicionalSolicitado] = Field(default_factory=list)
    notas: str = Field(default="", max_length=200)

    @field_validator("opciones", mode="before")
    @classmethod
    def _opcion_unica_como_lista(cls, opciones):
        """El mismo código suelto equivale a una lista de un elemento; no inventa opciones."""
        if isinstance(opciones, dict):
            return {
                tipo: [valor] if isinstance(valor, str) else valor
                for tipo, valor in opciones.items()
            }
        return opciones


# --- Resultado de validar ---------------------------------------------------------


class Problema(BaseModel):
    codigo: str  # para el motor, ej. "opcion_agotada"
    mensaje: str  # para el cliente
    opcion_original: str | None = None
    opcion_sugerida: str | None = None
    tipo: TipoGrupo | None = None


class Faltante(BaseModel):
    """Algo que el cliente aún debe elegir; el motor pregunta todo en un solo mensaje."""

    grupo: str
    nombre: str  # ej. "Salsa"
    cantidad: int  # cuántas faltan
    cantidad_total: int = 1  # cuántas lleva el producto en ese grupo
    opciones: list[Opcion]  # disponibles para elegir
    adicional: str | None = None  # si lo exige un adicional (ej. cuál topping extra)


class OpcionElegida(BaseModel):
    grupo: str
    codigo: str
    nombre: str


class AdicionalElegido(BaseModel):
    codigo: str
    nombre: str
    opcion: OpcionElegida | None = None
    cantidad: int
    precio_unitario: int


class ItemValidado(BaseModel):
    solicitud: ItemSolicitado
    nombre: str = ""  # nombre del producto ("" si no existe)
    precio_unitario: int = 0  # precio del producto, sin adicionales
    opciones: list[OpcionElegida] = []
    adicionales: list[AdicionalElegido] = []
    faltantes: list[Faltante] = []
    problemas: list[Problema] = []

    @computed_field
    @property
    def completo(self) -> bool:
        return not self.faltantes and not self.problemas

    @computed_field
    @property
    def total(self) -> int:
        extras = sum(a.precio_unitario * a.cantidad for a in self.adicionales)
        return (self.precio_unitario + extras) * self.solicitud.cantidad


class ResultadoCarrito(BaseModel):
    items: list[ItemValidado]
    subtotal: int
    domicilio: int
    total: int

    @computed_field
    @property
    def completo(self) -> bool:
        return bool(self.items) and all(i.completo for i in self.items)


# --- Reglas ------------------------------------------------------------------------


def normalizar_opciones(menu: Menu, item: ItemSolicitado) -> ItemSolicitado:
    """Reubica códigos exactos en un único grupo del producto, sin inventar elecciones.

    Si la IA duplicó una salsa también como sabor, conserva la salsa ya elegida.
    Los códigos desconocidos o ambiguos siguen sujetos a la validación estricta.
    No toca adicionales ni interpreta ingredientes de mezclas.
    """
    producto = next((p for p in menu.productos if p.id == item.producto and p.activo), None)
    if producto is None:
        return item.model_copy(deep=True)
    grupos = {g.id: g for g in menu.grupos_opciones}
    permitidas = {
        grupos[s.grupo].tipo: {o.id for o in grupos[s.grupo].opciones} for s in producto.selecciones
    }
    opciones: dict[TipoGrupo, list[str]] = {}
    for tipo, codigos in item.opciones.items():
        for codigo in codigos:
            destinos = [t for t, validas in permitidas.items() if codigo in validas]
            if codigo in permitidas.get(tipo, set()) or len(destinos) != 1:
                opciones.setdefault(tipo, []).append(codigo)
                continue
            destino = destinos[0]
            if codigo not in item.opciones.get(destino, []):
                opciones.setdefault(destino, []).append(codigo)
    resultado = item.model_copy(deep=True)
    resultado.opciones = {tipo: codigos for tipo, codigos in opciones.items() if codigos}
    return resultado


def validar_carrito(
    menu: Menu, items: list[ItemSolicitado], entrega: TipoEntrega | None = None
) -> ResultadoCarrito:
    """Valida cada ítem y calcula los montos. El domicilio solo se cobra si `entrega` es
    DOMICILIO (antes de elegir la entrega se muestra el total sin domicilio)."""
    validados = [validar_item(menu, item) for item in items]
    exceso = (
        len(items) > settings.order_max_items
        or sum(i.cantidad for i in items) > settings.order_max_units
    )
    if exceso and validados:
        validados[0].problemas.append(
            Problema(
                codigo="limite_pedido",
                mensaje=f"Para pedidos de más de {settings.order_max_units} unidades "
                f"o {settings.order_max_items} productos distintos, habla con el equipo.",
            )
        )
    if (
        validados
        and sum(i.cantidad * a.cantidad for i in items for a in i.adicionales)
        > settings.order_max_units
    ):
        validados[0].problemas.append(
            Problema(
                codigo="limite_adicionales",
                mensaje="Hay demasiados adicionales en el pedido. Consulta con el equipo.",
            )
        )
    subtotal = sum(i.total for i in validados)
    domicilio = menu.negocio.domicilio.costo if entrega is TipoEntrega.DOMICILIO else 0
    return ResultadoCarrito(
        items=validados, subtotal=subtotal, domicilio=domicilio, total=subtotal + domicilio
    )


def validar_item(menu: Menu, item: ItemSolicitado) -> ItemValidado:
    producto = next((p for p in menu.productos if p.id == item.producto and p.activo), None)
    if producto is None:
        return ItemValidado(
            solicitud=item,
            problemas=[
                Problema(
                    codigo="producto_no_existe",
                    mensaje=f"No tenemos '{item.producto}' en el menú.",
                )
            ],
        )

    grupos = {g.id: g for g in menu.grupos_opciones}
    resultado = ItemValidado(
        solicitud=item, nombre=producto.nombre, precio_unitario=producto.precio
    )
    if sum(a.cantidad for a in item.adicionales) > settings.order_max_units:
        resultado.problemas.append(
            Problema(
                codigo="limite_adicionales",
                mensaje="Hay demasiados adicionales. Consulta con el equipo.",
            )
        )
    _validar_selecciones(producto, item, grupos, resultado)
    _validar_adicionales(menu, item, grupos, resultado)
    return resultado


def _validar_selecciones(
    producto: Producto,
    item: ItemSolicitado,
    grupos: dict[str, GrupoOpciones],
    resultado: ItemValidado,
) -> None:
    """Lo que el producto exige elegir (un grupo por tipo, lo garantiza el esquema del menú)."""
    tipos_del_producto = {grupos[s.grupo].tipo for s in producto.selecciones}
    for tipo in item.opciones:
        if tipo not in tipos_del_producto:
            resultado.problemas.append(
                Problema(codigo="no_aplica", mensaje=f"{producto.nombre} no lleva {tipo.value}.")
            )

    for seleccion in producto.selecciones:
        grupo = grupos[seleccion.grupo]
        codigos = item.opciones.get(grupo.tipo, [])
        elegidas = _opciones_validas(
            grupo, codigos, producto.nombre, resultado.problemas, sugerir_mezcla=True
        )

        if not seleccion.permite_repetir and len(set(codigos)) != len(codigos):
            resultado.problemas.append(
                Problema(
                    codigo="opcion_repetida",
                    mensaje=f"En {producto.nombre} no se puede repetir {grupo.nombre.lower()}.",
                )
            )
        if len(elegidas) > seleccion.cantidad:
            resultado.problemas.append(
                Problema(
                    codigo="sobran_opciones",
                    mensaje=(
                        f"{producto.nombre} lleva {seleccion.cantidad} de "
                        f"{grupo.nombre.lower()} y elegiste {len(elegidas)}."
                    ),
                )
            )
            continue
        resultado.opciones += [
            OpcionElegida(grupo=grupo.id, codigo=o.id, nombre=o.nombre) for o in elegidas
        ]
        if len(elegidas) < seleccion.cantidad:
            resultado.faltantes.append(
                _faltante(grupo, seleccion.cantidad - len(elegidas), total=seleccion.cantidad)
            )


def _validar_adicionales(
    menu: Menu,
    item: ItemSolicitado,
    grupos: dict[str, GrupoOpciones],
    resultado: ItemValidado,
) -> None:
    adicionales = {a.id: a for a in menu.adicionales}
    for pedido in item.adicionales:
        adicional = adicionales.get(pedido.adicional)
        if adicional is None:
            resultado.problemas.append(
                Problema(
                    codigo="adicional_no_existe",
                    mensaje=f"No tenemos el adicional '{pedido.adicional}'.",
                )
            )
            continue

        opcion = None
        if adicional.grupo:
            grupo = grupos[adicional.grupo]
            if pedido.opcion is None:
                resultado.faltantes.append(_faltante(grupo, 1, adicional=adicional.id))
            else:
                validas = _opciones_validas(
                    grupo, [pedido.opcion], adicional.nombre, resultado.problemas
                )
                if not validas:
                    continue
                opcion = OpcionElegida(
                    grupo=grupo.id, codigo=validas[0].id, nombre=validas[0].nombre
                )
        elif pedido.opcion is not None:
            resultado.problemas.append(
                Problema(codigo="no_aplica", mensaje=f"{adicional.nombre} no lleva opciones.")
            )
            continue

        resultado.adicionales.append(
            AdicionalElegido(
                codigo=adicional.id,
                nombre=adicional.nombre,
                opcion=opcion,
                cantidad=pedido.cantidad,
                precio_unitario=adicional.precio,
            )
        )


def _opciones_validas(
    grupo: GrupoOpciones,
    codigos: list[str],
    para: str,
    problemas: list[Problema],
    *,
    sugerir_mezcla: bool = False,
) -> list[Opcion]:
    """Opciones del grupo que existen y están disponibles; las demás se reportan."""
    por_codigo = {o.id: o for o in grupo.opciones}
    validas = []
    for codigo in codigos:
        opcion = por_codigo.get(codigo)
        if opcion is None:
            sugerida = _mezcla_por_ingrediente(grupo, codigo) if sugerir_mezcla else None
            if sugerida:
                problemas.append(
                    Problema(
                        codigo="mezcla_por_confirmar",
                        mensaje=f"En {para}, '{codigo}' forma parte de {sugerida.nombre}. "
                        "No figura como sabor individual. ¿Quieres esa mezcla? "
                        "Confírmala o elige otra opción.",
                        opcion_original=codigo,
                        opcion_sugerida=sugerida.id,
                        tipo=grupo.tipo,
                    )
                )
                continue
            problemas.append(
                Problema(
                    codigo="opcion_no_existe",
                    mensaje=f"'{codigo}' no es una opción de {grupo.nombre.lower()} para {para}.",
                )
            )
        elif not opcion.disponible:
            problemas.append(
                Problema(
                    codigo="opcion_agotada", mensaje=f"{opcion.nombre} no está disponible hoy."
                )
            )
        else:
            validas.append(opcion)
    return validas


def _mezcla_por_ingrediente(grupo: GrupoOpciones, codigo: str) -> Opcion | None:
    """Sugiere únicamente una mezcla inequívoca del grupo; nunca cambia la selección."""
    coincidencias = []
    for opcion in grupo.opciones:
        componentes = re.search(r"\(([^()]+)\)", opcion.nombre)
        if componentes and opcion.disponible:
            ingredientes = re.split(r",|\s+y\s+", normalizar(componentes.group(1)))
            if normalizar(codigo.replace("_", " ")) in {i.strip() for i in ingredientes}:
                coincidencias.append(opcion)
    return coincidencias[0] if len(coincidencias) == 1 else None


def _faltante(
    grupo: GrupoOpciones, cantidad: int, adicional: str | None = None, *, total: int = 1
) -> Faltante:
    return Faltante(
        grupo=grupo.id,
        nombre=grupo.nombre,
        cantidad=cantidad,
        cantidad_total=total,
        opciones=[o for o in grupo.opciones if o.disponible],
        adicional=adicional,
    )
