"""Fixtures de BD: PostgreSQL real en una base aparte (heladeria_test).

En local, si Postgres no está arriba los tests de BD se saltan; en el CI fallan.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import settings

BACKEND = Path(__file__).resolve().parents[1]
URL_TEST = make_url(settings.database_url).set(database="heladeria_test")


def alembic_config(connection: Connection) -> Config:
    """Config de Alembic que migra sobre la conexión dada (ver migrations/env.py)."""
    cfg = Config(BACKEND / "alembic.ini")
    cfg.attributes["connection"] = connection
    return cfg


def _crear_bd_test() -> None:
    admin = create_engine(
        URL_TEST.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 3},
    )
    try:
        with admin.connect() as conn:
            existe = conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :nombre"),
                {"nombre": URL_TEST.database},
            )
            if not existe:
                conn.execute(text(f'CREATE DATABASE "{URL_TEST.database}"'))
    finally:
        admin.dispose()


@pytest.fixture(scope="session")
def bd_migrada() -> Iterator[Engine]:
    """BD de pruebas recreada desde cero y migrada a la última versión."""
    try:
        _crear_bd_test()
    except OperationalError:
        if os.environ.get("CI"):
            raise
        pytest.skip(f"PostgreSQL no disponible en {URL_TEST}: docker compose up -d db")

    engine = create_engine(URL_TEST)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        command.upgrade(alembic_config(conn), "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db(bd_migrada: Engine) -> Iterator[Session]:
    """Sesión dentro de una transacción que se revierte al terminar cada test."""
    with bd_migrada.connect() as conn:
        transaccion = conn.begin()
        with Session(bind=conn, join_transaction_mode="create_savepoint") as session:
            yield session
        transaccion.rollback()
