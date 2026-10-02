"""Esquema y validación del archivo semilla del menú (seeds/*.json).

Valida que todas las referencias cuadren (categorías, grupos de opciones)
para que un error en el JSON se detecte al arrancar y no en medio de un pedido.
"""

from pathlib import Path

from pydantic import BaseModel, Field, PositiveInt, model_validator

from app.enums import TipoGrupo


class Opcion(BaseModel):
    id: str
    nombre: str
    disponible: bool = True


class GrupoOpciones(BaseModel):
    id: str
    tipo: TipoGrupo
    nombre: str
    opciones: list[Opcion] = Field(min_length=1)

    @model_validator(mode="after")
    def ids_unicos(self):
        ids = [o.id for o in self.opciones]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Opciones repetidas en el grupo '{self.id}'")
        return self


class Seleccion(BaseModel):
    grupo: str
    cantidad: PositiveInt
    permite_repetir: bool = True  # ej. banana split: brownie, vainilla chips, brownie


class Producto(BaseModel):
    id: str
    nombre: str
    categoria: str
    precio: PositiveInt
    descripcion: str = ""
    activo: bool = True
    selecciones: list[Seleccion] = []


class Categoria(BaseModel):
    id: str
    nombre: str
    orden: int


class Adicional(BaseModel):
    id: str
    nombre: str
    precio: PositiveInt
    grupo: str | None = None  # si el adicional requiere elegir (ej. qué topping)


class MedioPago(BaseModel):
    id: str
    nombre: str
    cuenta: str | None = None
    titular: str | None = None
    requiere_comprobante: bool


class Domicilio(BaseModel):
    costo: int = 0
    nota: str = ""


class Negocio(BaseModel):
    nombre: str
    moneda: str = "COP"
    ciudad: str = ""
    horario: str = ""
    domicilio: Domicilio = Domicilio()


class Menu(BaseModel):
    version: int
    negocio: Negocio
    grupos_opciones: list[GrupoOpciones]
    categorias: list[Categoria]
    productos: list[Producto]
    adicionales: list[Adicional]
    medios_pago: list[MedioPago]

    @model_validator(mode="after")
    def referencias_validas(self):
        errores: list[str] = []

        def unicos(nombre: str, ids: list[str]) -> set[str]:
            if len(ids) != len(set(ids)):
                errores.append(f"IDs repetidos en {nombre}")
            return set(ids)

        grupos = unicos("grupos_opciones", [g.id for g in self.grupos_opciones])
        categorias = unicos("categorias", [c.id for c in self.categorias])
        unicos("productos", [p.id for p in self.productos])
        unicos("adicionales", [a.id for a in self.adicionales])
        unicos("medios_pago", [m.id for m in self.medios_pago])

        for p in self.productos:
            if p.categoria not in categorias:
                errores.append(f"Producto '{p.id}': categoría '{p.categoria}' no existe")
            for s in p.selecciones:
                if s.grupo not in grupos:
                    errores.append(f"Producto '{p.id}': grupo '{s.grupo}' no existe")
        for a in self.adicionales:
            if a.grupo and a.grupo not in grupos:
                errores.append(f"Adicional '{a.id}': grupo '{a.grupo}' no existe")
        for m in self.medios_pago:
            if m.requiere_comprobante and not m.cuenta:
                errores.append(f"Medio de pago '{m.id}' requiere comprobante pero no tiene cuenta")

        if errores:
            raise ValueError("Menú inválido:\n- " + "\n- ".join(errores))
        return self

    # Utilidades de consulta
    def producto(self, producto_id: str) -> Producto:
        return next(p for p in self.productos if p.id == producto_id)

    def grupo(self, grupo_id: str) -> GrupoOpciones:
        return next(g for g in self.grupos_opciones if g.id == grupo_id)


def cargar_menu(ruta: str | Path) -> Menu:
    return Menu.model_validate_json(Path(ruta).read_text(encoding="utf-8"))
