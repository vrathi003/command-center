"""Recurring subscriptions (streaming, SaaS, etc.)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiosqlite


@dataclass(frozen=True, slots=True)
class SubscriptionRow:
    id: int
    name: str
    provider: str | None
    category: str | None
    amount_paise: int
    billing_cycle: str
    next_billing_date: str | None
    notes: str | None
    is_active: bool


def monthly_equivalent_paise(amount_paise: int, billing_cycle: str) -> int:
    """Convert amount per billing period to a monthly equivalent in paise."""
    bc = billing_cycle.lower().strip()
    if bc == "weekly":
        return int(round(amount_paise * 52 / 12))
    if bc == "monthly":
        return amount_paise
    if bc == "quarterly":
        return int(round(amount_paise / 3))
    if bc == "yearly":
        return int(round(amount_paise / 12))
    return amount_paise


def _row_from_tuple(r: tuple[Any, ...]) -> SubscriptionRow:
    return SubscriptionRow(
        id=int(r[0]),
        name=str(r[1]),
        provider=str(r[2]) if r[2] is not None else None,
        category=str(r[3]) if r[3] is not None else None,
        amount_paise=int(r[4]),
        billing_cycle=str(r[5]),
        next_billing_date=str(r[6]) if r[6] is not None else None,
        notes=str(r[7]) if r[7] is not None else None,
        is_active=bool(int(r[8])),
    )


async def list_subscriptions(
    conn: aiosqlite.Connection,
    *,
    active_only: bool = False,
) -> list[SubscriptionRow]:
    if active_only:
        cur = await conn.execute(
            """
            SELECT id, name, provider, category, amount_paise, billing_cycle,
                   next_billing_date, notes, is_active
            FROM subscriptions
            WHERE is_active = 1
            ORDER BY name
            """,
        )
    else:
        cur = await conn.execute(
            """
            SELECT id, name, provider, category, amount_paise, billing_cycle,
                   next_billing_date, notes, is_active
            FROM subscriptions
            ORDER BY is_active DESC, name
            """,
        )
    rows = await cur.fetchall()
    return [_row_from_tuple(tuple(x)) for x in rows]


async def get_subscription(conn: aiosqlite.Connection, sub_id: int) -> SubscriptionRow | None:
    cur = await conn.execute(
        """
        SELECT id, name, provider, category, amount_paise, billing_cycle,
               next_billing_date, notes, is_active
        FROM subscriptions WHERE id = ?
        """,
        (sub_id,),
    )
    r = await cur.fetchone()
    return _row_from_tuple(tuple(r)) if r else None


async def insert_subscription(
    conn: aiosqlite.Connection,
    *,
    name: str,
    provider: str | None,
    category: str | None,
    amount_paise: int,
    billing_cycle: str,
    next_billing_date: str | None,
    notes: str | None,
    is_active: bool = True,
) -> int:
    cur = await conn.execute(
        """
        INSERT INTO subscriptions (
            name, provider, category, amount_paise, billing_cycle,
            next_billing_date, notes, is_active, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            name,
            provider,
            category,
            amount_paise,
            billing_cycle,
            next_billing_date,
            notes,
            1 if is_active else 0,
        ),
    )
    await conn.commit()
    last = cur.lastrowid
    if last is None:
        msg = "INSERT INTO subscriptions did not set lastrowid"
        raise RuntimeError(msg)
    return int(last)


async def update_subscription_row(conn: aiosqlite.Connection, row: SubscriptionRow) -> None:
    await conn.execute(
        """
        UPDATE subscriptions SET
            name = ?, provider = ?, category = ?, amount_paise = ?, billing_cycle = ?,
            next_billing_date = ?, notes = ?, is_active = ?,
            updated_at = datetime('now')
        WHERE id = ?
        """,
        (
            row.name,
            row.provider,
            row.category,
            row.amount_paise,
            row.billing_cycle,
            row.next_billing_date,
            row.notes,
            1 if row.is_active else 0,
            row.id,
        ),
    )
    await conn.commit()


async def delete_subscription(conn: aiosqlite.Connection, sub_id: int) -> bool:
    cur = await conn.execute("DELETE FROM subscriptions WHERE id = ?", (sub_id,))
    await conn.commit()
    return cur.rowcount > 0
