"""Key/value settings backed by SQLite."""

from __future__ import annotations

import aiosqlite

from finance_common.fy import current_fy_from_date
from finance_common.types import FYYear


async def get_value(conn: aiosqlite.Connection, key: str) -> str | None:
    cur = await conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = await cur.fetchone()
    return str(row[0]) if row else None


async def set_value(conn: aiosqlite.Connection, key: str, value: str) -> None:
    await conn.execute(
        """
        INSERT INTO settings (key, value, updated_at)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = datetime('now')
        """,
        (key, value),
    )
    await conn.commit()


async def get_current_fy(conn: aiosqlite.Connection) -> FYYear:
    raw = await get_value(conn, "current_fy")
    if raw:
        return FYYear(raw)
    return current_fy_from_date()


async def ensure_defaults(conn: aiosqlite.Connection) -> None:
    """Insert default settings if missing."""
    fy = current_fy_from_date()
    await conn.execute(
        """
        INSERT OR IGNORE INTO settings (key, value, updated_at)
        VALUES ('current_fy', ?, datetime('now'))
        """,
        (str(fy),),
    )
    await conn.commit()
