"""Net worth history API."""

from __future__ import annotations

from datetime import date
from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from finance_api.deps import get_conn
from finance_api.schemas.net_worth import NetWorthSnapshotOut, NetWorthSnapshotPost
from finance_api.services.net_worth_service import compute_totals_from_holdings
from finance_common.repositories import net_worth as nw_repo
from finance_common.repositories.net_worth import NetWorthSnapshotRow

router = APIRouter(prefix="/net-worth", tags=["net-worth"])


def _to_out(row: NetWorthSnapshotRow) -> NetWorthSnapshotOut:
    return NetWorthSnapshotOut(
        id=row.id,
        snapshot_date=row.snapshot_date,
        total_assets_paise=row.total_assets_paise,
        total_liabilities_paise=row.total_liabilities_paise,
        net_worth_paise=row.net_worth_paise,
    )


@router.get("/history", response_model=list[NetWorthSnapshotOut])
async def history(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    limit: int = 365,
) -> list[NetWorthSnapshotOut]:
    rows = await nw_repo.list_history(conn, limit=limit)
    return [_to_out(r) for r in rows]


@router.post("/snapshot", response_model=NetWorthSnapshotOut, status_code=201)
async def create_snapshot(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: NetWorthSnapshotPost,
) -> NetWorthSnapshotOut:
    snap_date = body.snapshot_date
    if snap_date is None:
        snap_date = date.today().isoformat()
    else:
        try:
            date.fromisoformat(snap_date)
        except ValueError as e:
            raise HTTPException(status_code=422, detail="snapshot_date must be YYYY-MM-DD") from e

    if body.computed_from_holdings:
        assets, liabilities, _ = await compute_totals_from_holdings(conn)
    else:
        if body.total_assets_paise is None or body.total_liabilities_paise is None:
            raise HTTPException(
                status_code=422,
                detail="total_assets_paise and total_liabilities_paise required for manual mode",
            )
        assets = body.total_assets_paise
        liabilities = body.total_liabilities_paise

    await nw_repo.upsert_snapshot(
        conn,
        snapshot_date=snap_date,
        total_assets_paise=assets,
        total_liabilities_paise=liabilities,
    )

    row = await nw_repo.get_by_snapshot_date(conn, snap_date)
    if row is None:
        raise HTTPException(status_code=500, detail="snapshot not found after insert")
    return _to_out(row)
