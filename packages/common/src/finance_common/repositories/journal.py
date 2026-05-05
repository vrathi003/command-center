"""Daily journal entries (one row per calendar date)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiosqlite


@dataclass(frozen=True, slots=True)
class JournalRow:
    entry_date: str
    body: str
    created_at: str
    updated_at: str


def _row(r: tuple[Any, ...]) -> JournalRow:
    return JournalRow(
        entry_date=str(r[0]),
        body=str(r[1]),
        created_at=str(r[2]),
        updated_at=str(r[3]),
    )


async def get_by_date(conn: aiosqlite.Connection, entry_date: str) -> JournalRow | None:
    cur = await conn.execute(
        """
        SELECT entry_date, body, created_at, updated_at
        FROM journal_entries WHERE entry_date = ?
        """,
        (entry_date,),
    )
    r = await cur.fetchone()
    return _row(tuple(r)) if r else None


async def upsert(conn: aiosqlite.Connection, *, entry_date: str, body: str) -> JournalRow:
    await conn.execute(
        """
        INSERT INTO journal_entries (entry_date, body, updated_at)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(entry_date) DO UPDATE SET
            body = excluded.body,
            updated_at = datetime('now')
        """,
        (entry_date, body),
    )
    await conn.commit()
    row = await get_by_date(conn, entry_date)
    if row is None:
        raise RuntimeError("journal upsert failed")
    return row


async def delete_by_date(conn: aiosqlite.Connection, entry_date: str) -> None:
    await conn.execute("DELETE FROM journal_entries WHERE entry_date = ?", (entry_date,))
    await conn.commit()


async def list_between(
    conn: aiosqlite.Connection, *, date_from: str, date_to: str
) -> list[JournalRow]:
    cur = await conn.execute(
        """
        SELECT entry_date, body, created_at, updated_at
        FROM journal_entries
        WHERE entry_date >= ? AND entry_date <= ?
        ORDER BY entry_date DESC
        """,
        (date_from, date_to),
    )
    rows = await cur.fetchall()
    return [_row(tuple(x)) for x in rows]
