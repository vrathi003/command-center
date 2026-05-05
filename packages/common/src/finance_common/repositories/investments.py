"""Market-traded holdings (MF, stocks, ETFs)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiosqlite


@dataclass(frozen=True, slots=True)
class InvestmentRow:
    id: int
    instrument: str
    type: str
    isin_code: str | None
    units: float | None
    avg_price_paise: int | None
    current_price_paise: int | None
    last_synced: str | None
    sector: str | None
    equity_tax_class: str


def _inv_tuple(r: tuple[Any, ...]) -> InvestmentRow:
    return InvestmentRow(
        id=int(r[0]),
        instrument=str(r[1]),
        type=str(r[2]),
        isin_code=str(r[3]) if r[3] is not None else None,
        units=float(r[4]) if r[4] is not None else None,
        avg_price_paise=int(r[5]) if r[5] is not None else None,
        current_price_paise=int(r[6]) if r[6] is not None else None,
        last_synced=str(r[7]) if r[7] is not None else None,
        sector=str(r[8]) if r[8] is not None else None,
        equity_tax_class=str(r[9]) if r[9] is not None else "unspecified",
    )


async def list_investments(conn: aiosqlite.Connection) -> list[InvestmentRow]:
    cur = await conn.execute(
        """
        SELECT id, instrument, type, isin_code, units,
               avg_price_paise, current_price_paise, last_synced,
               sector, equity_tax_class
        FROM investments
        ORDER BY type, instrument
        """,
    )
    rows = await cur.fetchall()
    return [_inv_tuple(tuple(r)) for r in rows]


async def get_investment(conn: aiosqlite.Connection, inv_id: int) -> InvestmentRow | None:
    cur = await conn.execute(
        """
        SELECT id, instrument, type, isin_code, units,
               avg_price_paise, current_price_paise, last_synced,
               sector, equity_tax_class
        FROM investments WHERE id = ?
        """,
        (inv_id,),
    )
    r = await cur.fetchone()
    return _inv_tuple(tuple(r)) if r else None


async def portfolio_totals(conn: aiosqlite.Connection) -> tuple[int, int, int, int]:
    """Cost basis (paise), market value (paise), unrealized P&L, row count."""
    cur = await conn.execute(
        """
        SELECT
            COALESCE(SUM(COALESCE(units, 0) * COALESCE(avg_price_paise, 0)), 0),
            COALESCE(SUM(COALESCE(units, 0) * COALESCE(current_price_paise, 0)), 0),
            COUNT(*)
        FROM investments
        """,
    )
    r = await cur.fetchone()
    if not r:
        return 0, 0, 0, 0
    cost = int(r[0])
    mkt = int(r[1])
    n = int(r[2])
    return cost, mkt, mkt - cost, n


async def update_investment_row(conn: aiosqlite.Connection, row: InvestmentRow) -> None:
    await conn.execute(
        """
        UPDATE investments SET
            instrument = ?, type = ?, isin_code = ?, units = ?,
            avg_price_paise = ?, current_price_paise = ?, last_synced = ?,
            sector = ?, equity_tax_class = ?,
            updated_at = datetime('now')
        WHERE id = ?
        """,
        (
            row.instrument,
            row.type,
            row.isin_code,
            row.units,
            row.avg_price_paise,
            row.current_price_paise,
            row.last_synced,
            row.sector,
            row.equity_tax_class,
            row.id,
        ),
    )
    await conn.commit()


async def insert_investment(
    conn: aiosqlite.Connection,
    *,
    instrument: str,
    type_: str,
    isin_code: str | None,
    units: float | None,
    avg_price_paise: int | None,
    current_price_paise: int | None,
    last_synced: str | None = None,
    sector: str | None = None,
    equity_tax_class: str = "unspecified",
) -> int:
    cur = await conn.execute(
        """
        INSERT INTO investments (
            instrument, type, isin_code, units,
            avg_price_paise, current_price_paise, last_synced,
            sector, equity_tax_class, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            instrument,
            type_,
            isin_code,
            units,
            avg_price_paise,
            current_price_paise,
            last_synced,
            sector,
            equity_tax_class,
        ),
    )
    await conn.commit()
    last = cur.lastrowid
    if last is None:
        msg = "INSERT INTO investments did not set lastrowid"
        raise RuntimeError(msg)
    return int(last)


async def delete_investment(conn: aiosqlite.Connection, inv_id: int) -> bool:
    cur = await conn.execute("DELETE FROM investments WHERE id = ?", (inv_id,))
    await conn.commit()
    return cur.rowcount > 0
