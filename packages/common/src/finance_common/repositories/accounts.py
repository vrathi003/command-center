"""Account CRUD — wraps the `accounts` table."""

from __future__ import annotations

from dataclasses import dataclass

import aiosqlite


@dataclass(frozen=True, slots=True)
class AccountRow:
    id: int
    name: str
    type: str
    institution: str | None
    currency: str
    is_active: bool


def _row_to_account(r: tuple) -> AccountRow:  # type: ignore[type-arg]
    return AccountRow(
        id=int(r[0]),
        name=str(r[1]),
        type=str(r[2]),
        institution=str(r[3]) if r[3] else None,
        currency=str(r[4]),
        is_active=bool(r[5]),
    )


async def list_accounts(
    conn: aiosqlite.Connection, *, active_only: bool = False
) -> list[AccountRow]:
    if active_only:
        cur = await conn.execute(
            "SELECT id, name, type, institution, currency, is_active "
            "FROM accounts WHERE is_active = 1 ORDER BY name"
        )
    else:
        cur = await conn.execute(
            "SELECT id, name, type, institution, currency, is_active "
            "FROM accounts ORDER BY name"
        )
    rows = await cur.fetchall()
    return [_row_to_account(r) for r in rows]


async def get_account(conn: aiosqlite.Connection, account_id: int) -> AccountRow | None:
    cur = await conn.execute(
        "SELECT id, name, type, institution, currency, is_active "
        "FROM accounts WHERE id = ?",
        (account_id,),
    )
    r = await cur.fetchone()
    return _row_to_account(r) if r else None


async def get_account_by_name(
    conn: aiosqlite.Connection, name: str
) -> AccountRow | None:
    cur = await conn.execute(
        "SELECT id, name, type, institution, currency, is_active "
        "FROM accounts WHERE name = ? COLLATE NOCASE LIMIT 1",
        (name,),
    )
    r = await cur.fetchone()
    return _row_to_account(r) if r else None


async def create_account(
    conn: aiosqlite.Connection,
    *,
    name: str,
    type: str,
    institution: str | None,
    currency: str = "INR",
) -> int:
    cur = await conn.execute(
        """
        INSERT INTO accounts (name, type, institution, currency, updated_at)
        VALUES (?, ?, ?, ?, datetime('now'))
        """,
        (name, type, institution, currency),
    )
    await conn.commit()
    last = cur.lastrowid
    if last is None:
        raise RuntimeError("INSERT INTO accounts did not set lastrowid")
    return int(last)


async def update_account(
    conn: aiosqlite.Connection,
    account_id: int,
    *,
    name: str,
    type: str,
    institution: str | None,
    currency: str,
    is_active: bool,
) -> bool:
    cur = await conn.execute(
        """
        UPDATE accounts
        SET name = ?, type = ?, institution = ?, currency = ?,
            is_active = ?, updated_at = datetime('now')
        WHERE id = ?
        """,
        (name, type, institution, currency, int(is_active), account_id),
    )
    await conn.commit()
    return cur.rowcount > 0


async def delete_account(conn: aiosqlite.Connection, account_id: int) -> bool:
    cur = await conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
    await conn.commit()
    return cur.rowcount > 0
