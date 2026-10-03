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
from app.pedidos.carrito import ResultadoCarrito


def crear_pedido(
    session: Session,
    conversacion: Conversacion,
    resultado: ResultadoCarrito,
    tipo_entrega: TipoEntrega,
    direccion: str | None,
    medio_pago: str,
    estado: EstadoPedido,
) -> Pedido:
    """Guarda el pedido con copia de nombres y precios (si el menú cambia, el pedido no)."""
    if not resultado.completo:
        raise ValueError("Solo se registran carritos completos")

    productos = {p.codigo: p for p in session.scalars(select(Producto))}
    adicionales = {a.codigo: a for a in session.scalars(select(Adicional))}
    opciones = {
        (o.grupo.codigo, o.codigo): o
        for o in session.scalars(select(Opcion).options(joinedload(Opcion.grupo)))
    }
    medio = session.scalars(select(MedioPago).where(MedioPago.codigo == medio_pago)).one()

    pedido = Pedido(
        cliente=conversacion.cliente,
        conversacion=conversacion,
        estado=estado,
        tipo_entrega=tipo_entrega,
        subtotal=resultado.subtotal,
        domicilio=resultado.domicilio,
        total=resultado.total,
        direccion=direccion if tipo_entrega is TipoEntrega.DOMICILIO else None,
        medio_pago=medio,
    )
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
