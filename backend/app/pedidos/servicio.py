"""Registro de pedidos en la BD a partir de un carrito ya validado por el código."""

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.enums import EstadoPedido, TipoEntrega
from app.models import (
    Adicional,
    Conversacion,
    ItemAdicional,
    ItemOpcion,
    ItemPedido,
    MedioPago,
    Opcion,
    Pedido,
    Producto,
)
from app.pedidos.carrito import AdicionalSolicitado, ItemSolicitado, ResultadoCarrito


def editable(pedido: Pedido) -> bool:
    if pedido.comprobante_url or pedido.estado not in {
        EstadoPedido.PENDIENTE_PAGO,
        EstadoPedido.EN_PREPARACION,
    }:
        return False
    return pedido.estado is EstadoPedido.PENDIENTE_PAGO or (
        pedido.medio_pago is not None and not pedido.medio_pago.requiere_comprobante
    )


def recuperar_carrito(pedido: Pedido) -> list[ItemSolicitado]:
    carrito = []
    for item in pedido.items:
        opciones = {}
        for elegida in item.opciones:
            opciones.setdefault(elegida.opcion.grupo.tipo, []).append(elegida.opcion.codigo)
        carrito.append(
            ItemSolicitado(
                producto=item.producto.codigo,
                cantidad=item.cantidad,
                opciones=opciones,
                notas=item.notas or "",
                adicionales=[
                    AdicionalSolicitado(
                        adicional=a.adicional.codigo,
                        cantidad=a.cantidad,
                        opcion=a.opcion.codigo if a.opcion else None,
                    )
                    for a in item.adicionales
                ],
            )
        )
    return carrito


def crear_pedido(
    session: Session,
    conversacion: Conversacion,
    resultado: ResultadoCarrito,
    tipo_entrega: TipoEntrega,
    direccion: str | None,
    medio_pago: str,
    estado: EstadoPedido,
    *,
    pedido_existente: Pedido | None = None,
) -> Pedido:
    """Guarda el pedido con copia de nombres y precios (si el menú cambia, el pedido no)."""
    if not resultado.completo:
        raise ValueError("Solo se registran carritos completos")
    if pedido_existente is not None and (
        pedido_existente.cliente_id != conversacion.cliente_id
        or pedido_existente.conversacion_id != conversacion.id
        or not editable(pedido_existente)
    ):
        raise ValueError("Este pedido no admite cambios automáticos")

    productos = {p.codigo: p for p in session.scalars(select(Producto))}
    adicionales = {a.codigo: a for a in session.scalars(select(Adicional))}
    opciones = {
        (o.grupo.codigo, o.codigo): o
        for o in session.scalars(select(Opcion).options(joinedload(Opcion.grupo)))
    }
    medio = session.scalars(select(MedioPago).where(MedioPago.codigo == medio_pago)).one()

    pedido = pedido_existente or Pedido(cliente=conversacion.cliente, conversacion=conversacion)
    if pedido_existente is not None:
        pedido.items.clear()
        session.flush()
    pedido.estado = estado
    pedido.tipo_entrega = tipo_entrega
    pedido.subtotal, pedido.domicilio, pedido.total = (
        resultado.subtotal,
        resultado.domicilio,
        resultado.total,
    )
    pedido.direccion = direccion if tipo_entrega is TipoEntrega.DOMICILIO else None
    pedido.medio_pago = medio
    for item in resultado.items:
        pedido.items.append(
            ItemPedido(
                producto=productos[item.solicitud.producto],
                nombre=item.nombre,
                cantidad=item.solicitud.cantidad,
                precio_unitario=item.precio_unitario,
                notas=item.solicitud.notas or None,
                opciones=[
                    ItemOpcion(opcion=opciones[(o.grupo, o.codigo)], nombre=o.nombre, posicion=i)
                    for i, o in enumerate(item.opciones)
                ],
                adicionales=[
                    ItemAdicional(
                        adicional=adicionales[a.codigo],
                        opcion=opciones[(a.opcion.grupo, a.opcion.codigo)] if a.opcion else None,
                        nombre=a.nombre + (f" ({a.opcion.nombre})" if a.opcion else ""),
                        cantidad=a.cantidad,
                        precio_unitario=a.precio_unitario,
                    )
                    for a in item.adicionales
                ],
            )
        )
    session.add(pedido)
    session.flush()
    return pedido
