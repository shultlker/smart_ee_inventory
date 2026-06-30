"""Lightweight SQLite schema upgrades for existing databases (no Alembic)."""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

logger = logging.getLogger(__name__)

_INVENTORY_OPERATION_COLUMNS: tuple[tuple[str, str], ...] = (
    ("entity_type", "VARCHAR(32) DEFAULT 'slot_material' NOT NULL"),
    ("asset_id", "INTEGER"),
    ("status", "VARCHAR(32) DEFAULT 'confirmed' NOT NULL"),
    ("user_name", "VARCHAR(64)"),
    ("project_name", "VARCHAR(128)"),
    ("consumed_qty", "INTEGER DEFAULT 0 NOT NULL"),
)


def _column_names(connection: Connection, table: str) -> set[str]:
    return {col["name"] for col in inspect(connection).get_columns(table)}


def _table_exists(connection: Connection, table: str) -> bool:
    return table in inspect(connection).get_table_names()


def upgrade_schema(connection: Connection) -> None:
    """Add missing columns/tables after ``create_all`` on an older DB file."""
    if not _table_exists(connection, "inventory_operations"):
        return

    existing = _column_names(connection, "inventory_operations")
    for name, ddl in _INVENTORY_OPERATION_COLUMNS:
        if name in existing:
            continue
        connection.execute(text(f"ALTER TABLE inventory_operations ADD COLUMN {name} {ddl}"))
        logger.info("Migrated inventory_operations: added column %s", name)
