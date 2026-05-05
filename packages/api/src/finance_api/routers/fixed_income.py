"""Fixed income instruments."""

from __future__ import annotations

from dataclasses import replace
from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from finance_api.deps import get_conn
from finance_api.schemas.investment import (
    FixedIncomeCreateBody,
    FixedIncomeOut,
    FixedIncomePutBody,
    FixedIncomeSummaryOut,
)
from finance_common.repositories import fixed_income as fi_repo
from finance_common.repositories.fixed_income import FixedIncomeRow

router = APIRouter(prefix="/fixed-income", tags=["fixed-income"])


def _to_out(row: FixedIncomeRow) -> FixedIncomeOut:
    return FixedIncomeOut(
        id=row.id,
        institution=row.institution,
        type=row.type,
        principal_paise=row.principal_paise,
        rate_percent=row.rate_percent,
        start_date=row.start_date,
        maturity_date=row.maturity_date,
    )


def _merge_fi(existing: FixedIncomeRow, body: FixedIncomePutBody) -> FixedIncomeRow:
    patch = body.model_dump(exclude_unset=True)
    return replace(existing, **patch)


@router.get("/summary", response_model=FixedIncomeSummaryOut)
async def fixed_income_summary_route(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> FixedIncomeSummaryOut:
    total, n = await fi_repo.total_principal(conn)
    return FixedIncomeSummaryOut(total_principal_paise=total, instrument_count=n)


@router.post("/", response_model=FixedIncomeOut, status_code=201)
async def create_fixed_income(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: FixedIncomeCreateBody,
) -> FixedIncomeOut:
    fid = await fi_repo.insert_fixed_income(
        conn,
        institution=body.institution,
        type_=body.type,
        principal_paise=body.principal_paise,
        rate_percent=body.rate_percent,
        start_date=body.start_date,
        maturity_date=body.maturity_date,
    )
    row = await fi_repo.get_fixed_income(conn, fid)
    if row is None:
        raise HTTPException(status_code=500, detail="fixed income not found after insert")
    return _to_out(row)


@router.get("/", response_model=list[FixedIncomeOut])
async def list_fixed_income(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> list[FixedIncomeOut]:
    rows = await fi_repo.list_fixed_income(conn)
    return [_to_out(r) for r in rows]


@router.get("/{fi_id}", response_model=FixedIncomeOut)
async def get_fixed_income(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    fi_id: int,
) -> FixedIncomeOut:
    row = await fi_repo.get_fixed_income(conn, fi_id)
    if row is None:
        raise HTTPException(status_code=404, detail="fixed income not found")
    return _to_out(row)


@router.put("/{fi_id}", response_model=FixedIncomeOut)
async def put_fixed_income(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    fi_id: int,
    body: FixedIncomePutBody,
) -> FixedIncomeOut:
    existing = await fi_repo.get_fixed_income(conn, fi_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="fixed income not found")
    merged = _merge_fi(existing, body)
    await fi_repo.update_fixed_income_row(conn, merged)
    return _to_out(merged)


@router.delete("/{fi_id}", status_code=204)
async def delete_fixed_income(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    fi_id: int,
) -> None:
    ok = await fi_repo.delete_fixed_income(conn, fi_id)
    if not ok:
        raise HTTPException(status_code=404, detail="fixed income not found")
