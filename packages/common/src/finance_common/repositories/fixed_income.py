"""Fixed income / guaranteed instruments (FD, PPF, etc.)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiosqlite


@dataclass(frozen=True, slots=True)
class FixedIncomeRow:
    id: int
    institution: str
    type: str
    principal_paise: int
    rate_percent: float | None
    start_date: str | None
    maturity_date: str | None


def _fi_tuple(r: tuple[Any, ...]) -> FixedIncomeRow:
    return FixedIncomeRow(
        id=int(r[0]),
        institution=str(r[1]),
        type=str(r[2]),
        principal_paise=int(r[3]),
        rate_percent=float(r[4]) if r[4] is not None else None,
        start_date=str(r[5]) if r[5] is not None else None,
        maturity_date=str(r[6]) if r[6] is not None else None,
    )


async def list_fixed_income(conn: aiosqlite.Connection) -> list[FixedIncomeRow]:
    cur = await conn.execute(
        """
        SELECT id, institution, type, principal_paise, rate_percent, start_date, maturity_date
        FROM fixed_income
        ORDER BY maturity_date IS NULL, maturity_date, institution
        """,
    )
    rows = await cur.fetchall()
    return [_fi_tuple(tuple(r)) for r in rows]


async def total_principal(conn: aiosqlite.Connection) -> tuple[int, int]:
    """Sum of principal_paise and row count."""
    cur = await conn.execute(
        """
        SELECT COALESCE(SUM(principal_paise), 0), COUNT(*) FROM fixed_income
        """,
    )
    r = await cur.fetchone()
    if not r:
        return 0, 0
    return int(r[0]), int(r[1])


async def get_fixed_income(conn: aiosqlite.Connection, fi_id: int) -> FixedIncomeRow | None:
    cur = await conn.execute(
        """
        SELECT id, institution, type, principal_paise, rate_percent, start_date, maturity_date
        FROM fixed_income WHERE id = ?
        """,
        (fi_id,),
    )
    r = await cur.fetchone()
    return _fi_tuple(tuple(r)) if r else None


async def insert_fixed_income(
    conn: aiosqlite.Connection,
    *,
    institution: str,
    type_: str,
    principal_paise: int,
    rate_percent: float | None,
    start_date: str | None,
    maturity_date: str | None,
) -> int:
    cur = await conn.execute(
        """
        INSERT INTO fixed_income (
            institution, type, principal_paise, rate_percent, start_date, maturity_date, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (institution, type_, principal_paise, rate_percent, start_date, maturity_date),
    )
    await conn.commit()
    last = cur.lastrowid
    if last is None:
        msg = "INSERT INTO fixed_income did not set lastrowid"
        raise RuntimeError(msg)
    return int(last)


async def update_fixed_income_row(conn: aiosqlite.Connection, row: FixedIncomeRow) -> None:
    await conn.execute(
        """
        UPDATE fixed_income SET
            institution = ?, type = ?, principal_paise = ?, rate_percent = ?,
            start_date = ?, maturity_date = ?, updated_at = datetime('now')
        WHERE id = ?
        """,
        (
            row.institution,
            row.type,
            row.principal_paise,
            row.rate_percent,
            row.start_date,
            row.maturity_date,
            row.id,
        ),
    )
    await conn.commit()


async def delete_fixed_income(conn: aiosqlite.Connection, fi_id: int) -> bool:
    cur = await conn.execute("DELETE FROM fixed_income WHERE id = ?", (fi_id,))
    await conn.commit()
    return cur.rowcount > 0
