"""Conexión a PostgreSQL y base declarativa de los modelos."""

from collections.abc import Iterator
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

# Nombres deterministas para índices y constraints: Alembic los necesita para
# poder borrarlos o renombrarlos en migraciones futuras.
CONVENCION_NOMBRES = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONVENCION_NOMBRES)
    type_annotation_map = {datetime: DateTime(timezone=True)}


def enum_texto(enum_cls: type[StrEnum]) -> Enum:
    """Enum guardado como VARCHAR con su valor, sin tipo ENUM de Postgres ni CHECK.

    Agregar un valor nuevo no requiere migración; SQLAlchemy valida al escribir.
    """
    return Enum(
        enum_cls,
        native_enum=False,
        create_constraint=False,
        length=30,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )


engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Dependencia de FastAPI: una sesión por request."""
    with SessionLocal() as session:
        yield session
