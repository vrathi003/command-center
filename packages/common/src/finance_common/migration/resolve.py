"""Resolve legacy account references to ledger account ids."""

from __future__ import annotations

import aiosqlite


async def resolve_account_id(
    conn: aiosqlite.Connection,
    *,
    account_id: int | None,
    account_name: str | None,
) -> int | None:
    """Return a valid account id, falling back to an unambiguous legacy name."""
    if account_id is not None:
        cursor = await conn.execute("SELECT id FROM accounts WHERE id = ?", (account_id,))
        row = await cursor.fetchone()
        if row is not None:
            return int(row[0])

    if not account_name:
        return None

    cursor = await conn.execute("SELECT id FROM accounts WHERE name = ?", (account_name,))
    row = await cursor.fetchone()
    if row is not None:
        return int(row[0])

    cursor = await conn.execute("SELECT id, name FROM accounts")
    matches = [
        row
        for row in await cursor.fetchall()
        if str(row[1]).casefold() == account_name.casefold()
    ]
    return int(matches[0][0]) if len(matches) == 1 else None
