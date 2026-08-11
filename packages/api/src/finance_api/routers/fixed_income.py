"""Fixed income instruments."""

from __future__ import annotations

from dataclasses import replace
from datetime import date as date_cls
from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Request

from finance_api.deps import get_conn
from finance_api.deps_ledger import require_ledger_writes
from finance_api.schemas.investment import (
    FixedIncomeCreateBody,
    FixedIncomeOut,
    FixedIncomePutBody,
    FixedIncomeSummaryOut,
    RecordFixedIncomeDepositBody,
    RecordFixedIncomeMaturityBody,
    RecordFixedIncomeTradeOut,
)
from finance_api.services.investment_ledger import (
    ensure_fixed_income_account_and_seed,
    record_fixed_income_deposit,
    record_fixed_income_maturity,
)
from finance_common.ledger.errors import LedgerError
from finance_common.project_config import load_project_config
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
        account_id=row.account_id,
    )


def _merge_fi(existing: FixedIncomeRow, body: FixedIncomePutBody) -> FixedIncomeRow:
    patch = body.model_dump(exclude_unset=True)
    return replace(existing, **patch)


async def _ensure_fixed_income_row_if_ledger(
    conn: aiosqlite.Connection, row: FixedIncomeRow
) -> FixedIncomeRow:
    project_config = await load_project_config(conn)
    if project_config.ledger_engine != "double_entry":
        return row
    await ensure_fixed_income_account_and_seed(conn, row)
    refreshed = await fi_repo.get_fixed_income(conn, row.id)
    return refreshed if refreshed is not None else row


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
    row = await _ensure_fixed_income_row_if_ledger(conn, row)
    return _to_out(row)


@router.get("/", response_model=list[FixedIncomeOut])
async def list_fixed_income(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> list[FixedIncomeOut]:
    rows = await fi_repo.list_fixed_income(conn)
    project_config = await load_project_config(conn)
    if project_config.ledger_engine == "double_entry":
        ensured: list[FixedIncomeRow] = []
        for row in rows:
            ensured.append(await _ensure_fixed_income_row_if_ledger(conn, row))
        rows = ensured
    return [_to_out(r) for r in rows]


@router.get("/{fi_id}", response_model=FixedIncomeOut)
async def get_fixed_income(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    fi_id: int,
) -> FixedIncomeOut:
    row = await fi_repo.get_fixed_income(conn, fi_id)
    if row is None:
        raise HTTPException(status_code=404, detail="fixed income not found")
    row = await _ensure_fixed_income_row_if_ledger(conn, row)
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


async def _require_double_entry(conn: aiosqlite.Connection) -> None:
    project_config = await load_project_config(conn)
    if project_config.ledger_engine != "double_entry":
        raise HTTPException(
            status_code=422,
            detail="record requires double_entry ledger engine",
        )


def _parse_trade_date(date_str: str) -> date_cls:
    try:
        return date_cls.fromisoformat(date_str)
    except ValueError as e:
        raise HTTPException(status_code=422, detail="invalid date") from e


@router.post(
    "/{fi_id}/record-deposit",
    response_model=RecordFixedIncomeTradeOut,
    status_code=201,
)
async def record_deposit(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    request: Request,
    fi_id: int,
    body: RecordFixedIncomeDepositBody,
) -> RecordFixedIncomeTradeOut:
    """Post fixed-income deposit through the ledger."""
    row = await fi_repo.get_fixed_income(conn, fi_id)
    if row is None:
        raise HTTPException(status_code=404, detail="fixed income not found")

    await _require_double_entry(conn)
    require_ledger_writes(request)

    try:
        ledger_transaction_id, updated = await record_fixed_income_deposit(
            conn,
            fi_row=row,
            tx_date=_parse_trade_date(body.date),
            amount_paise=body.amount_paise,
            bank_account_id=body.bank_account_id,
        )
    except LedgerError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    return RecordFixedIncomeTradeOut(
        ledger_transaction_id=ledger_transaction_id,
        fixed_income=_to_out(updated),
    )


@router.post(
    "/{fi_id}/record-maturity",
    response_model=RecordFixedIncomeTradeOut,
    status_code=201,
)
async def record_maturity(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    request: Request,
    fi_id: int,
    body: RecordFixedIncomeMaturityBody,
) -> RecordFixedIncomeTradeOut:
    """Post fixed-income maturity/withdrawal through the ledger."""
    row = await fi_repo.get_fixed_income(conn, fi_id)
    if row is None:
        raise HTTPException(status_code=404, detail="fixed income not found")

    await _require_double_entry(conn)
    require_ledger_writes(request)

    amount_paise = body.amount_paise if body.amount_paise is not None else row.principal_paise

    try:
        ledger_transaction_id, updated = await record_fixed_income_maturity(
            conn,
            fi_row=row,
            tx_date=_parse_trade_date(body.date),
            amount_paise=amount_paise,
            bank_account_id=body.bank_account_id,
        )
    except LedgerError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    return RecordFixedIncomeTradeOut(
        ledger_transaction_id=ledger_transaction_id,
        fixed_income=_to_out(updated),
    )
