"""Loan and liability rows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiosqlite


@dataclass(frozen=True, slots=True)
class DebtRow:
    id: int
    name: str
    lender: str | None
    type: str
    original_amount_paise: int | None
    current_balance_paise: int
    emi_paise: int | None
    rate_percent: float | None
    start_date: str | None
    next_emi_date: str | None
    status: str
    tenure_months: int | None
    first_emi_date: str | None
    full_emi_start_date: str | None


@dataclass(frozen=True, slots=True)
class LoanDisbursalRow:
    id: int
    debt_id: int
    disbursal_date: str
    amount_paise: int
    notes: str | None
    created_at: str


_DEBT_SELECT = """
    SELECT id, name, lender, type, original_amount_paise, current_balance_paise,
           emi_paise, rate_percent, start_date, next_emi_date, status,
           tenure_months, first_emi_date, full_emi_start_date
    FROM debts
"""


def _row_from_tuple(r: tuple[Any, ...]) -> DebtRow:
    return DebtRow(
        id=int(r[0]),
        name=str(r[1]),
        lender=str(r[2]) if r[2] is not None else None,
        type=str(r[3]),
        original_amount_paise=int(r[4]) if r[4] is not None else None,
        current_balance_paise=int(r[5]),
        emi_paise=int(r[6]) if r[6] is not None else None,
        rate_percent=float(r[7]) if r[7] is not None else None,
        start_date=str(r[8]) if r[8] is not None else None,
        next_emi_date=str(r[9]) if r[9] is not None else None,
        status=str(r[10]),
        tenure_months=int(r[11]) if r[11] is not None else None,
        first_emi_date=str(r[12]) if r[12] is not None else None,
        full_emi_start_date=str(r[13]) if r[13] is not None else None,
    )


async def list_debts(
    conn: aiosqlite.Connection,
    *,
    status: str | None = None,
) -> list[DebtRow]:
    if status:
        cur = await conn.execute(
            _DEBT_SELECT + " WHERE status = ? ORDER BY name",
            (status,),
        )
    else:
        cur = await conn.execute(
            _DEBT_SELECT + " ORDER BY status, name",
        )
    rows = await cur.fetchall()
    return [_row_from_tuple(tuple(r)) for r in rows]


async def get_debt(conn: aiosqlite.Connection, debt_id: int) -> DebtRow | None:
    cur = await conn.execute(
        _DEBT_SELECT + " WHERE id = ?",
        (debt_id,),
    )
    r = await cur.fetchone()
    return _row_from_tuple(tuple(r)) if r else None


async def update_debt_row(conn: aiosqlite.Connection, row: DebtRow) -> None:
    """Persist all fields for an existing debt row."""
    await conn.execute(
        """
        UPDATE debts SET
            name = ?, lender = ?, type = ?, original_amount_paise = ?,
            current_balance_paise = ?, emi_paise = ?, rate_percent = ?,
            start_date = ?, next_emi_date = ?, status = ?,
            tenure_months = ?, first_emi_date = ?, full_emi_start_date = ?,
            updated_at = datetime('now')
        WHERE id = ?
        """,
        (
            row.name,
            row.lender,
            row.type,
            row.original_amount_paise,
            row.current_balance_paise,
            row.emi_paise,
            row.rate_percent,
            row.start_date,
            row.next_emi_date,
            row.status,
            row.tenure_months,
            row.first_emi_date,
            row.full_emi_start_date,
            row.id,
        ),
    )
    await conn.commit()


async def insert_debt(
    conn: aiosqlite.Connection,
    *,
    name: str,
    lender: str | None,
    type_: str,
    original_amount_paise: int | None,
    current_balance_paise: int,
    emi_paise: int | None,
    rate_percent: float | None,
    start_date: str | None,
    next_emi_date: str | None,
    status: str = "active",
    tenure_months: int | None = None,
    first_emi_date: str | None = None,
    full_emi_start_date: str | None = None,
) -> int:
    cur = await conn.execute(
        """
        INSERT INTO debts (
            name, lender, type, original_amount_paise, current_balance_paise,
            emi_paise, rate_percent, start_date, next_emi_date, status,
            tenure_months, first_emi_date, full_emi_start_date,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            name,
            lender,
            type_,
            original_amount_paise,
            current_balance_paise,
            emi_paise,
            rate_percent,
            start_date,
            next_emi_date,
            status,
            tenure_months,
            first_emi_date,
            full_emi_start_date,
        ),
    )
    await conn.commit()
    last = cur.lastrowid
    if last is None:
        msg = "INSERT INTO debts did not set lastrowid"
        raise RuntimeError(msg)
    return int(last)


async def aggregate_active(conn: aiosqlite.Connection) -> tuple[int, int, int]:
    """Total outstanding, total monthly EMI (where EMI set), count active."""
    cur = await conn.execute(
        """
        SELECT COALESCE(SUM(current_balance_paise), 0),
               COALESCE(SUM(COALESCE(emi_paise, 0)), 0),
               COUNT(*)
        FROM debts WHERE status = 'active'
        """,
    )
    r = await cur.fetchone()
    if not r:
        return 0, 0, 0
    return int(r[0]), int(r[1]), int(r[2])


async def next_emi_hint(conn: aiosqlite.Connection) -> tuple[str | None, str | None]:
    """Earliest next_emi_date among active debts (ISO date), and that debt's name."""
    cur = await conn.execute(
        """
        SELECT name, next_emi_date FROM debts
        WHERE status = 'active' AND next_emi_date IS NOT NULL
        ORDER BY next_emi_date ASC
        LIMIT 1
        """,
    )
    r = await cur.fetchone()
    if not r:
        return None, None
    return str(r[1]), str(r[0])


async def delete_debt(conn: aiosqlite.Connection, debt_id: int) -> bool:
    cur = await conn.execute("DELETE FROM debts WHERE id = ?", (debt_id,))
    await conn.commit()
    return cur.rowcount > 0


# ── Loan disbursals ──────────────────────────────────────────────────────────

def _disbursal_from_tuple(r: tuple[Any, ...]) -> LoanDisbursalRow:
    return LoanDisbursalRow(
        id=int(r[0]),
        debt_id=int(r[1]),
        disbursal_date=str(r[2]),
        amount_paise=int(r[3]),
        notes=str(r[4]) if r[4] is not None else None,
        created_at=str(r[5]),
    )


async def list_disbursals(
    conn: aiosqlite.Connection, debt_id: int
) -> list[LoanDisbursalRow]:
    cur = await conn.execute(
        """
        SELECT id, debt_id, disbursal_date, amount_paise, notes, created_at
        FROM loan_disbursals
        WHERE debt_id = ?
        ORDER BY disbursal_date ASC, id ASC
        """,
        (debt_id,),
    )
    rows = await cur.fetchall()
    return [_disbursal_from_tuple(tuple(r)) for r in rows]


async def insert_disbursal(
    conn: aiosqlite.Connection,
    *,
    debt_id: int,
    disbursal_date: str,
    amount_paise: int,
    notes: str | None = None,
) -> int:
    cur = await conn.execute(
        """
        INSERT INTO loan_disbursals (debt_id, disbursal_date, amount_paise, notes)
        VALUES (?, ?, ?, ?)
        """,
        (debt_id, disbursal_date, amount_paise, notes),
    )
    await conn.commit()
    last = cur.lastrowid
    if last is None:
        raise RuntimeError("INSERT INTO loan_disbursals did not set lastrowid")
    return int(last)


async def delete_disbursal(
    conn: aiosqlite.Connection, disbursal_id: int, debt_id: int
) -> bool:
    cur = await conn.execute(
        "DELETE FROM loan_disbursals WHERE id = ? AND debt_id = ?",
        (disbursal_id, debt_id),
    )
    await conn.commit()
    return cur.rowcount > 0
