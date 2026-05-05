"""Multiple income streams (salary, rental, freelance, …)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiosqlite

from finance_common.types import IncomeFrequency


@dataclass(frozen=True, slots=True)
class IncomeSourceRow:
    id: int
    name: str
    type: str
    amount_paise: int | None
    frequency: str
    taxability: str
    is_active: bool


def _row(r: tuple[Any, ...]) -> IncomeSourceRow:
    return IncomeSourceRow(
        id=int(r[0]),
        name=str(r[1]),
        type=str(r[2]),
        amount_paise=int(r[3]) if r[3] is not None else None,
        frequency=str(r[4]),
        taxability=str(r[5]),
        is_active=bool(r[6]),
    )


def monthly_equivalent_paise(amount_paise: int | None, frequency: str) -> int:
    """Normalize recurring income to an approximate monthly paise amount."""
    if amount_paise is None or amount_paise <= 0:
        return 0
    try:
        freq = IncomeFrequency(frequency)
    except ValueError:
        return 0
    if freq is IncomeFrequency.MONTHLY:
        return amount_paise
    if freq is IncomeFrequency.QUARTERLY:
        return amount_paise // 3
    if freq is IncomeFrequency.ANNUAL:
        return amount_paise // 12
    return 0


async def list_income_sources(
    conn: aiosqlite.Connection,
    *,
    active_only: bool = True,
) -> list[IncomeSourceRow]:
    if active_only:
        cur = await conn.execute(
            """
            SELECT id, name, type, amount_paise, frequency, taxability, is_active
            FROM income_sources WHERE is_active = 1
            ORDER BY type, name
            """,
        )
    else:
        cur = await conn.execute(
            """
            SELECT id, name, type, amount_paise, frequency, taxability, is_active
            FROM income_sources
            ORDER BY is_active DESC, type, name
            """,
        )
    rows = await cur.fetchall()
    return [_row(tuple(x)) for x in rows]


async def get_income_source(conn: aiosqlite.Connection, income_id: int) -> IncomeSourceRow | None:
    cur = await conn.execute(
        """
        SELECT id, name, type, amount_paise, frequency, taxability, is_active
        FROM income_sources WHERE id = ?
        """,
        (income_id,),
    )
    r = await cur.fetchone()
    return _row(tuple(r)) if r else None


async def total_monthly_equivalent_paise(conn: aiosqlite.Connection) -> int:
    """Sum of monthly-equivalent paise for all active streams."""
    rows = await list_income_sources(conn, active_only=True)
    return sum(monthly_equivalent_paise(r.amount_paise, r.frequency) for r in rows)


async def insert_income_source(
    conn: aiosqlite.Connection,
    *,
    name: str,
    type_: str,
    amount_paise: int | None,
    frequency: str,
    taxability: str,
    is_active: bool = True,
) -> int:
    cur = await conn.execute(
        """
        INSERT INTO income_sources (
            name, type, amount_paise, frequency, taxability, is_active, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (name, type_, amount_paise, frequency, taxability, 1 if is_active else 0),
    )
    await conn.commit()
    last = cur.lastrowid
    if last is None:
        msg = "INSERT INTO income_sources did not set lastrowid"
        raise RuntimeError(msg)
    return int(last)


async def update_income_source(
    conn: aiosqlite.Connection,
    *,
    income_id: int,
    name: str,
    type_: str,
    amount_paise: int | None,
    frequency: str,
    taxability: str,
    is_active: bool,
) -> None:
    await conn.execute(
        """
        UPDATE income_sources SET
            name = ?, type = ?, amount_paise = ?, frequency = ?, taxability = ?,
            is_active = ?, updated_at = datetime('now')
        WHERE id = ?
        """,
        (name, type_, amount_paise, frequency, taxability, 1 if is_active else 0, income_id),
    )
    await conn.commit()


async def delete_income_source(conn: aiosqlite.Connection, income_id: int) -> bool:
    cur = await conn.execute("DELETE FROM income_sources WHERE id = ?", (income_id,))
    await conn.commit()
    return cur.rowcount > 0
