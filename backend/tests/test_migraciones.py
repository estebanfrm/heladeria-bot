"""Las migraciones se aplican y revierten limpio, y coinciden con los modelos."""

from alembic import command
from sqlalchemy import Connection, inspect

import app.models  # noqa: F401  registra los modelos en Base.metadata
from app.db import Base
from tests.conftest import alembic_config

TABLAS_MODELOS = set(Base.metadata.tables)


def _tablas(conn: Connection) -> set[str]:
    return set(inspect(conn).get_table_names()) - {"alembic_version"}


def test_downgrade_y_upgrade_completos(bd_migrada):
    with bd_migrada.begin() as conn:
        cfg = alembic_config(conn)
        assert _tablas(conn) == TABLAS_MODELOS

        command.downgrade(cfg, "base")
        assert _tablas(conn) == set()

        command.upgrade(cfg, "head")
        assert _tablas(conn) == TABLAS_MODELOS


def test_modelos_y_migraciones_sincronizados(bd_migrada):
    """Falla si se cambió un modelo sin crear su migración:
    uv run alembic revision --autogenerate -m "..."
    """
    with bd_migrada.connect() as conn:
        command.check(alembic_config(conn))
