"""Account CRUD — wraps the `accounts` table."""

from __future__ import annotations

from dataclasses import dataclass

import aiosqlite

_ACCOUNT_CLASS_BY_TYPE = {
    "credit_card": "liability_cc",
    "loan": "liability_loan",
    "investment": "asset_investment",
}


def _default_account_class(account_type: str) -> str:
    return _ACCOUNT_CLASS_BY_TYPE.get(account_type, "asset_cash")


@dataclass(frozen=True, slots=True)
class AccountRow:
    id: int
    name: str
    type: str
    account_class: str
    institution: str | None
    currency: str
    is_active: bool


def _row_to_account(r: aiosqlite.Row) -> AccountRow:
    return AccountRow(
        id=int(r[0]),
        name=str(r[1]),
        type=str(r[2]),
        account_class=str(r[3]),
        institution=str(r[4]) if r[4] else None,
        currency=str(r[5]),
        is_active=bool(r[6]),
    )


async def list_accounts(
    conn: aiosqlite.Connection, *, active_only: bool = False
) -> list[AccountRow]:
    if active_only:
        cur = await conn.execute(
            "SELECT id, name, type, account_class, institution, currency, is_active "
            "FROM accounts WHERE is_active = 1 ORDER BY name"
        )
    else:
        cur = await conn.execute(
            "SELECT id, name, type, account_class, institution, currency, is_active "
            "FROM accounts ORDER BY name"
        )
    rows = await cur.fetchall()
    return [_row_to_account(r) for r in rows]


async def get_account(conn: aiosqlite.Connection, account_id: int) -> AccountRow | None:
    cur = await conn.execute(
        "SELECT id, name, type, account_class, institution, currency, is_active "
        "FROM accounts WHERE id = ?",
        (account_id,),
    )
    r = await cur.fetchone()
    return _row_to_account(r) if r else None


async def get_account_by_name(
    conn: aiosqlite.Connection, name: str
) -> AccountRow | None:
    cur = await conn.execute(
        "SELECT id, name, type, account_class, institution, currency, is_active "
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
    account_class: str | None = None,
) -> int:
    resolved_account_class = account_class or _default_account_class(type)
    cur = await conn.execute(
        """
        INSERT INTO accounts (name, type, account_class, institution, currency, updated_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
        """,
        (name, type, resolved_account_class, institution, currency),
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
    account_class: str | None = None,
) -> bool:
    resolved_account_class = account_class or _default_account_class(type)
    cur = await conn.execute(
        """
        UPDATE accounts
        SET name = ?, type = ?, account_class = ?, institution = ?, currency = ?,
            is_active = ?, updated_at = datetime('now')
        WHERE id = ?
        """,
        (
            name,
            type,
            resolved_account_class,
            institution,
            currency,
            int(is_active),
            account_id,
        ),
    )
    await conn.commit()
    return cur.rowcount > 0


async def delete_account(conn: aiosqlite.Connection, account_id: int) -> bool:
    cur = await conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
    await conn.commit()
    return cur.rowcount > 0
