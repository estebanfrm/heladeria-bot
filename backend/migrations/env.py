"""Entorno de Alembic: la URL sale de .env (app.config) y el esquema de app.models."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, create_engine, pool

import app.models  # noqa: F401  registra todos los modelos en Base.metadata
from app.config import settings
from app.db import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Genera el SQL sin conectarse (alembic upgrade head --sql)."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _migrar(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Los tests pasan su propia conexión (BD de pruebas) en config.attributes
    connection = config.attributes.get("connection")
    if connection is not None:
        _migrar(connection)
        return

    engine = create_engine(settings.database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        _migrar(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
