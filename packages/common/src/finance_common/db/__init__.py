"""SQLite schema bootstrap and connection helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
from loguru import logger

from finance_common.config import AppSettings
from finance_common.db.migrations import apply_migrations
from finance_common.repositories.settings_repo import ensure_defaults


def schema_sql() -> str:
    """Load bundled schema DDL (wheel, editable, or source tree)."""
    here = Path(__file__).resolve().parent
    return (here / "schema.sql").read_text(encoding="utf-8")


async def ensure_database(db_path: Path) -> None:
    """Create parent directory if needed and apply schema."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as conn:
        await conn.executescript(schema_sql())
        await ensure_defaults(conn)
        await apply_migrations(conn)
        await conn.commit()
    logger.info("Database ready at {}", db_path)


@asynccontextmanager
async def open_db(db_path: Path) -> AsyncIterator[aiosqlite.Connection]:
    """Open a connection with foreign keys enabled."""
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute("PRAGMA foreign_keys = ON")
        yield conn


def default_db_path() -> Path:
    return AppSettings().db_path
