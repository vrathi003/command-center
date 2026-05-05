"""Net worth snapshot history (manual or derived)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiosqlite


@dataclass(frozen=True, slots=True)
class NetWorthSnapshotRow:
    id: int
    snapshot_date: str
    total_assets_paise: int
    total_liabilities_paise: int
    net_worth_paise: int


def _row(r: tuple[Any, ...]) -> NetWorthSnapshotRow:
    return NetWorthSnapshotRow(
        id=int(r[0]),
        snapshot_date=str(r[1]),
        total_assets_paise=int(r[2]),
        total_liabilities_paise=int(r[3]),
        net_worth_paise=int(r[4]),
    )


async def list_history(
    conn: aiosqlite.Connection,
    *,
    limit: int = 365,
) -> list[NetWorthSnapshotRow]:
    """Latest `limit` snapshots, oldest-first (for charts)."""
    lim = max(1, min(limit, 5000))
    cur = await conn.execute(
        """
        SELECT id, snapshot_date, total_assets_paise, total_liabilities_paise, net_worth_paise
        FROM (
            SELECT id, snapshot_date, total_assets_paise, total_liabilities_paise, net_worth_paise
            FROM net_worth_history
            ORDER BY snapshot_date DESC
            LIMIT ?
        ) AS nw_window
        ORDER BY snapshot_date ASC
        """,
        (lim,),
    )
    rows = await cur.fetchall()
    return [_row(tuple(x)) for x in rows]


async def get_by_snapshot_date(
    conn: aiosqlite.Connection,
    snapshot_date: str,
) -> NetWorthSnapshotRow | None:
    cur = await conn.execute(
        """
        SELECT id, snapshot_date, total_assets_paise, total_liabilities_paise, net_worth_paise
        FROM net_worth_history WHERE snapshot_date = ?
        """,
        (snapshot_date,),
    )
    r = await cur.fetchone()
    return _row(tuple(r)) if r else None


async def upsert_snapshot(
    conn: aiosqlite.Connection,
    *,
    snapshot_date: str,
    total_assets_paise: int,
    total_liabilities_paise: int,
) -> None:
    net = total_assets_paise - total_liabilities_paise
    await conn.execute(
        """
        INSERT INTO net_worth_history (
            snapshot_date, total_assets_paise, total_liabilities_paise, net_worth_paise
        ) VALUES (?, ?, ?, ?)
        ON CONFLICT(snapshot_date) DO UPDATE SET
            total_assets_paise = excluded.total_assets_paise,
            total_liabilities_paise = excluded.total_liabilities_paise,
            net_worth_paise = excluded.net_worth_paise
        """,
        (snapshot_date, total_assets_paise, total_liabilities_paise, net),
    )
    await conn.commit()
