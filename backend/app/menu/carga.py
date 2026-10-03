"""Carga del menú semilla (seeds/*.json) a la BD y lectura del menú vigente.

Aplicar el seed lo vuelve la fuente de verdad: sobrescribe lo editado en el panel.
Por eso el contenedor solo lo aplica al arrancar si trae una `version` mayor.

Uso (desde backend/):
    uv run python -m app.menu.carga          # aplica SEED_FILE a la BD
    uv run python -m app.menu.carga --auto   # solo si la BD no tiene menú o hay versión nueva
"""

import argparse

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.db import SessionLocal
from app.menu import schema
from app.menu.schema import Menu, cargar_menu
from app.models import (
    Adicional,
    Categoria,
    GrupoOpcion,
    MedioPago,
    Negocio,
    Opcion,
    Producto,
    ProductoSeleccion,
)


class MenuNoCargado(RuntimeError):
    pass


def _por_codigo[M: (Categoria, GrupoOpcion, Producto, Adicional, MedioPago)](
    session: Session, modelo: type[M]
) -> dict[str, M]:
    return {fila.codigo: fila for fila in session.scalars(select(modelo))}


# --- Seed → BD ---------------------------------------------------------------


def aplicar_menu(session: Session, menu: Menu) -> None:
    """Sincroniza la BD con el menú semilla por `codigo`. Es idempotente.

    Lo que ya no está en el seed no se borra (puede estar en pedidos viejos): queda `activo=False`.
    """
    with session.no_autoflush:
        _aplicar_negocio(session, menu)
        categorias = _aplicar_categorias(session, menu)
        grupos = _aplicar_grupos(session, menu)
        _aplicar_productos(session, menu, categorias, grupos)
        _aplicar_adicionales(session, menu, grupos)
        _aplicar_medios_pago(session, menu)
    session.flush()


def _aplicar_negocio(session: Session, menu: Menu) -> None:
    negocio = session.scalar(select(Negocio)) or Negocio()
    negocio.nombre = menu.negocio.nombre
    negocio.moneda = menu.negocio.moneda
    negocio.ciudad = menu.negocio.ciudad
    negocio.horario = menu.negocio.horario
    negocio.costo_domicilio = menu.negocio.domicilio.costo
    negocio.nota_domicilio = menu.negocio.domicilio.nota
    negocio.version_menu = menu.version
    session.add(negocio)


def _aplicar_categorias(session: Session, menu: Menu) -> dict[str, Categoria]:
    existentes = _por_codigo(session, Categoria)
    categorias = {}
    for c in menu.categorias:
        categoria = existentes.pop(c.id, None) or Categoria(codigo=c.id)
        categoria.nombre, categoria.orden, categoria.activo = c.nombre, c.orden, True
        session.add(categoria)
        categorias[c.id] = categoria
    for sobrante in existentes.values():
        sobrante.activo = False
    return categorias


def _aplicar_grupos(session: Session, menu: Menu) -> dict[str, GrupoOpcion]:
    existentes = _por_codigo(session, GrupoOpcion)
    grupos = {}
    for g in menu.grupos_opciones:
        grupo = existentes.pop(g.id, None) or GrupoOpcion(codigo=g.id)
        grupo.tipo, grupo.nombre, grupo.activo = g.tipo, g.nombre, True
        opciones = {o.codigo: o for o in grupo.opciones}
        for o in g.opciones:
            opcion = opciones.pop(o.id, None)
            if opcion is None:
                opcion = Opcion(codigo=o.id)
                grupo.opciones.append(opcion)
            opcion.nombre, opcion.disponible, opcion.activo = o.nombre, o.disponible, True
        for sobrante in opciones.values():
            sobrante.activo = False
        session.add(grupo)
        grupos[g.id] = grupo
    for sobrante in existentes.values():
        sobrante.activo = False
    return grupos


def _aplicar_productos(
    session: Session,
    menu: Menu,
    categorias: dict[str, Categoria],
    grupos: dict[str, GrupoOpcion],
) -> None:
    existentes = _por_codigo(session, Producto)
    for p in menu.productos:
        producto = existentes.pop(p.id, None) or Producto(codigo=p.id)
        producto.nombre, producto.precio = p.nombre, p.precio
        producto.descripcion, producto.activo = p.descripcion, p.activo
        producto.categoria = categorias[p.categoria]
        # Se actualizan en sitio (la PK es producto+grupo); las que sobran se borran
        actuales = {s.grupo.codigo: s for s in producto.selecciones}
        selecciones = []
        for orden, s in enumerate(p.selecciones):
            seleccion = actuales.pop(s.grupo, None) or ProductoSeleccion(grupo=grupos[s.grupo])
            seleccion.cantidad, seleccion.permite_repetir = s.cantidad, s.permite_repetir
            seleccion.orden = orden
            selecciones.append(seleccion)
        producto.selecciones = selecciones
        session.add(producto)
    for sobrante in existentes.values():
        sobrante.activo = False


def _aplicar_adicionales(session: Session, menu: Menu, grupos: dict[str, GrupoOpcion]) -> None:
    existentes = _por_codigo(session, Adicional)
    for a in menu.adicionales:
        adicional = existentes.pop(a.id, None) or Adicional(codigo=a.id)
        adicional.nombre, adicional.precio, adicional.activo = a.nombre, a.precio, True
        adicional.grupo = grupos[a.grupo] if a.grupo else None
        session.add(adicional)
    for sobrante in existentes.values():
        sobrante.activo = False


def _aplicar_medios_pago(session: Session, menu: Menu) -> None:
    existentes = _por_codigo(session, MedioPago)
    for m in menu.medios_pago:
        medio = existentes.pop(m.id, None) or MedioPago(codigo=m.id)
        medio.nombre, medio.numero_cuenta, medio.titular = m.nombre, m.cuenta, m.titular
        medio.requiere_comprobante, medio.activo = m.requiere_comprobante, True
        session.add(medio)
    for sobrante in existentes.values():
        sobrante.activo = False


def hay_version_nueva(session: Session, menu: Menu) -> bool:
    """True si la BD no tiene menú o el seed trae una versión mayor que la aplicada."""
    aplicada = session.scalar(select(Negocio.version_menu))
    return aplicada is None or menu.version > aplicada


# --- BD → Menu -----------------------------------------------------------------


def leer_menu(session: Session) -> Menu:
    """Carta vigente desde la BD (solo lo activo), con el mismo esquema que el seed."""
    negocio = session.scalar(select(Negocio))
    if negocio is None:
        raise MenuNoCargado("El menú no está cargado: uv run python -m app.menu.carga")

    grupos = session.scalars(
        select(GrupoOpcion)
        .where(GrupoOpcion.activo)
        .options(selectinload(GrupoOpcion.opciones))
        .order_by(GrupoOpcion.id)
    ).all()
    categorias = session.scalars(
        select(Categoria).where(Categoria.activo).order_by(Categoria.orden, Categoria.id)
    ).all()
    productos = session.scalars(
        select(Producto)
        .where(Producto.activo)
        .options(
            selectinload(Producto.categoria),
            selectinload(Producto.selecciones).selectinload(ProductoSeleccion.grupo),
        )
        .order_by(Producto.id)
    ).all()
    adicionales = session.scalars(
        select(Adicional)
        .where(Adicional.activo)
        .options(selectinload(Adicional.grupo))
        .order_by(Adicional.id)
    ).all()
    medios = session.scalars(select(MedioPago).where(MedioPago.activo).order_by(MedioPago.id)).all()

    return Menu(
        version=negocio.version_menu,
        negocio=schema.Negocio(
            nombre=negocio.nombre,
            moneda=negocio.moneda,
            ciudad=negocio.ciudad,
            horario=negocio.horario,
            domicilio=schema.Domicilio(costo=negocio.costo_domicilio, nota=negocio.nota_domicilio),
        ),
        grupos_opciones=[
            schema.GrupoOpciones(
                id=g.codigo,
                tipo=g.tipo,
                nombre=g.nombre,
                opciones=[
                    schema.Opcion(id=o.codigo, nombre=o.nombre, disponible=o.disponible)
                    for o in g.opciones
                    if o.activo
                ],
            )
            for g in grupos
        ],
        categorias=[
            schema.Categoria(id=c.codigo, nombre=c.nombre, orden=c.orden) for c in categorias
        ],
        productos=[
            schema.Producto(
                id=p.codigo,
                nombre=p.nombre,
                categoria=p.categoria.codigo,
                precio=p.precio,
                descripcion=p.descripcion,
                activo=p.activo,
                selecciones=[
                    schema.Seleccion(
                        grupo=s.grupo.codigo, cantidad=s.cantidad, permite_repetir=s.permite_repetir
                    )
                    for s in p.selecciones
                ],
            )
            for p in productos
        ],
        adicionales=[
            schema.Adicional(
                id=a.codigo,
                nombre=a.nombre,
                precio=a.precio,
                grupo=a.grupo.codigo if a.grupo else None,
            )
            for a in adicionales
        ],
        medios_pago=[
            schema.MedioPago(
                id=m.codigo,
                nombre=m.nombre,
                cuenta=m.numero_cuenta,
                titular=m.titular,
                requiere_comprobante=m.requiere_comprobante,
            )
            for m in medios
        ],
    )


# --- CLI -------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Aplica el menú semilla (SEED_FILE) a la BD.")
    parser.add_argument(
        "--auto",
        action="store_true",
        help="solo si la BD no tiene menú o el seed trae una versión mayor (arranque)",
    )
    args = parser.parse_args(argv)

    menu = cargar_menu(settings.seed_file)
    with SessionLocal() as session:
        if args.auto and not hay_version_nueva(session, menu):
            print(f"Menú v{menu.version} ya aplicado; no se recarga.")
            return
        aplicar_menu(session, menu)
        session.commit()
    print(
        f"Menú '{menu.negocio.nombre}' v{menu.version} aplicado: "
        f"{len(menu.productos)} productos, {len(menu.grupos_opciones)} grupos de opciones, "
        f"{len(menu.adicionales)} adicionales, {len(menu.medios_pago)} medios de pago."
    )


if __name__ == "__main__":
    main()
