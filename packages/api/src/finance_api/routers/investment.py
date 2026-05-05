"""Listed investments (MF, stocks, ETFs)."""

from __future__ import annotations

from dataclasses import replace
from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from finance_api.deps import get_conn
from finance_api.schemas.investment import (
    InvestmentCreateBody,
    InvestmentOut,
    InvestmentPutBody,
    PortfolioSummaryOut,
)
from finance_common.repositories import investments as inv_repo
from finance_common.repositories.investments import InvestmentRow

router = APIRouter(prefix="/investments", tags=["investments"])


def _derived(row: InvestmentRow) -> tuple[int | None, int | None, int | None]:
    if row.units is None or row.units <= 0:
        return None, None, None
    cost = None
    mkt = None
    if row.avg_price_paise is not None:
        cost = int(round(row.units * row.avg_price_paise))
    if row.current_price_paise is not None:
        mkt = int(round(row.units * row.current_price_paise))
    un = None
    if cost is not None and mkt is not None:
        un = mkt - cost
    return cost, mkt, un


def _to_out(row: InvestmentRow) -> InvestmentOut:
    cost, mkt, un = _derived(row)
    return InvestmentOut(
        id=row.id,
        instrument=row.instrument,
        type=row.type,
        isin_code=row.isin_code,
        units=row.units,
        avg_price_paise=row.avg_price_paise,
        current_price_paise=row.current_price_paise,
        last_synced=row.last_synced,
        sector=row.sector,
        equity_tax_class=row.equity_tax_class,
        cost_basis_paise=cost,
        market_value_paise=mkt,
        unrealized_paise=un,
    )


def _merge_row(existing: InvestmentRow, body: InvestmentPutBody) -> InvestmentRow:
    patch = body.model_dump(exclude_unset=True)
    return replace(existing, **patch)


@router.get("/portfolio-summary", response_model=PortfolioSummaryOut)
async def portfolio_summary(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> PortfolioSummaryOut:
    cost, mkt, unreal, n = await inv_repo.portfolio_totals(conn)
    return PortfolioSummaryOut(
        cost_basis_paise=cost,
        market_value_paise=mkt,
        unrealized_paise=unreal,
        holdings_count=n,
    )


@router.get("/", response_model=list[InvestmentOut])
async def list_investments(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> list[InvestmentOut]:
    rows = await inv_repo.list_investments(conn)
    return [_to_out(r) for r in rows]


@router.post("/", response_model=InvestmentOut, status_code=201)
async def create_investment(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: InvestmentCreateBody,
) -> InvestmentOut:
    new_id = await inv_repo.insert_investment(
        conn,
        instrument=body.instrument,
        type_=body.type,
        isin_code=body.isin_code,
        units=body.units,
        avg_price_paise=body.avg_price_paise,
        current_price_paise=body.current_price_paise,
        last_synced=None,
        sector=body.sector,
        equity_tax_class=body.equity_tax_class or "unspecified",
    )
    row = await inv_repo.get_investment(conn, new_id)
    if row is None:
        raise HTTPException(status_code=500, detail="Failed to load new investment")
    return _to_out(row)


@router.get("/{inv_id}", response_model=InvestmentOut)
async def get_investment(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    inv_id: int,
) -> InvestmentOut:
    row = await inv_repo.get_investment(conn, inv_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Investment not found")
    return _to_out(row)


@router.put("/{inv_id}", response_model=InvestmentOut)
async def put_investment(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    inv_id: int,
    body: InvestmentPutBody,
) -> InvestmentOut:
    existing = await inv_repo.get_investment(conn, inv_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Investment not found")
    merged = _merge_row(existing, body)
    await inv_repo.update_investment_row(conn, merged)
    return _to_out(merged)


@router.delete("/{inv_id}", status_code=204)
async def delete_investment(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    inv_id: int,
) -> None:
    ok = await inv_repo.delete_investment(conn, inv_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Investment not found")
