"""Selección guiada: una elección por paso y páginas que caben en listas de WhatsApp."""

from dataclasses import dataclass

from app.conversacion.mensajes import Boton, Respuesta, descripcion_item
from app.enums import TipoGrupo
from app.menu.schema import Menu, Opcion
from app.pedidos.carrito import Faltante, ResultadoCarrito

OPCIONES_POR_PAGINA = 7  # deja espacio para anterior, siguiente y reiniciar (≤10 filas)


@dataclass(frozen=True)
class Paso:
    indice: int
    faltante: Faltante
    tipo: TipoGrupo
    opciones: list[Opcion]


def siguiente(menu: Menu, resultado: ResultadoCarrito) -> Paso | None:
    for indice, item in enumerate(resultado.items):
        if not item.faltantes:
            continue
        faltante = item.faltantes[0]
        grupo = menu.grupo(faltante.grupo)
        opciones = faltante.opciones
        if not faltante.adicional:
            seleccion = next(
                s for s in menu.producto(item.solicitud.producto).selecciones if s.grupo == grupo.id
            )
            if not seleccion.permite_repetir:
                elegidas = {o.codigo for o in item.opciones if o.grupo == grupo.id}
                opciones = [o for o in opciones if o.id not in elegidas]
        return Paso(indice, faltante, grupo.tipo, opciones)
    return None


def reiniciar(token: str) -> Boton:
    return Boton(
        id=f"seleccion-reiniciar:{token}",
        titulo="Elegir de nuevo",
        descripcion="Volver a elegir sabores, salsas y toppings.",
    )


def presentar(
    menu: Menu, resultado: ResultadoCarrito, token: str, pagina: int = 0
) -> Respuesta | None:
    paso = siguiente(menu, resultado)
    if paso is None:
        return None
    item = resultado.items[paso.indice]
    f = paso.faltante
    paginas = max(1, (len(paso.opciones) + OPCIONES_POR_PAGINA - 1) // OPCIONES_POR_PAGINA)
    pagina = max(0, min(pagina, paginas - 1))
    inicio = pagina * OPCIONES_POR_PAGINA
    botones = [
        Boton(
            id=f"seleccion:{token}:{o.id}",
            titulo=o.nombre.split(" (")[0][:24],
            descripcion=o.nombre if len(o.nombre) > 24 else "",
        )
        for o in paso.opciones[inicio : inicio + OPCIONES_POR_PAGINA]
    ]
    if pagina:
        botones.append(Boton(id=f"seleccion-pagina:{token}:{pagina - 1}", titulo="← Anteriores"))
    if pagina + 1 < paginas:
        botones.append(Boton(id=f"seleccion-pagina:{token}:{pagina + 1}", titulo="Más opciones →"))
    botones.append(reiniciar(token))
    elegido = descripcion_item(item)
    etiqueta = f.nombre
    if f.adicional:
        etiqueta = next(a.nombre for a in menu.adicionales if a.id == f.adicional)
    lineas = [f"*{item.nombre}*" + (f" ({elegido})" if elegido else "")]
    if item.solicitud.cantidad > 1:
        lineas.append(f"Estas opciones se aplican a las {item.solicitud.cantidad} unidades.")
    elegidas = f.cantidad_total - f.cantidad
    lineas.append(f"Elige {etiqueta.lower()}: {elegidas + 1} de {f.cantidad_total}.")
    if elegidas:
        pendiente = "falta" if f.cantidad == 1 else "faltan"
        lineas.append(f"Te {pendiente} {f.cantidad} de {f.cantidad_total} en este grupo.")
    if item.problemas:
        lineas.insert(0, f"⚠️ {item.problemas[0].mensaje}")
    if not paso.opciones:
        lineas.append(
            "No hay opciones disponibles para completar este paso. Consulta con el equipo."
        )
    else:
        lineas.append("Pulsa «Ver opciones» y toca tu elección.")
    if paginas > 1:
        lineas.append(f"Página {pagina + 1} de {paginas}.")
    return Respuesta(texto="\n".join(lineas), botones=botones, lista=True)
