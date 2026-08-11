"""Income streams API (multiple sources)."""

from __future__ import annotations

from datetime import date as date_cls
from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Request

from finance_api.deps import get_conn
from finance_api.deps_ledger import require_ledger_writes
from finance_api.schemas.income import (
    IncomeCreate,
    IncomeOut,
    IncomePut,
    IncomeSummaryOut,
    RecordIncomeBody,
    RecordIncomeOut,
)
from finance_api.services.income_ledger import post_income_credit
from finance_common.ledger.errors import LedgerError
from finance_common.project_config import load_project_config
from finance_common.repositories import accounts as accounts_repo
from finance_common.repositories import income_sources as income_repo
from finance_common.repositories.income_sources import IncomeSourceRow, monthly_equivalent_paise
from finance_common.types import IncomeFrequency, Taxability

router = APIRouter(prefix="/income", tags=["income"])


def _parse_frequency(raw: str) -> IncomeFrequency:
    try:
        return IncomeFrequency(raw.strip().lower())
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail=f"frequency must be one of: {', '.join(x.value for x in IncomeFrequency)}",
        ) from e


def _parse_taxability(raw: str) -> Taxability:
    try:
        return Taxability(raw.strip().lower())
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail=f"taxability must be one of: {', '.join(x.value for x in Taxability)}",
        ) from e


def _to_out(row: IncomeSourceRow) -> IncomeOut:
    eq = monthly_equivalent_paise(row.amount_paise, row.frequency)
    return IncomeOut(
        id=row.id,
        name=row.name,
        type=row.type,
        amount_paise=row.amount_paise,
        frequency=row.frequency,
        taxability=row.taxability,
        is_active=row.is_active,
        default_account_id=row.default_account_id,
        category=row.category,
        monthly_equivalent_paise=eq,
    )


@router.get("/summary", response_model=IncomeSummaryOut)
async def income_summary(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> IncomeSummaryOut:
    rows = await income_repo.list_income_sources(conn, active_only=True)
    t = await income_repo.total_monthly_equivalent_paise(conn)
    return IncomeSummaryOut(stream_count=len(rows), total_monthly_equivalent_paise=t)


@router.get("/", response_model=list[IncomeOut])
async def list_income(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    include_inactive: bool = False,
) -> list[IncomeOut]:
    rows = await income_repo.list_income_sources(conn, active_only=not include_inactive)
    return [_to_out(r) for r in rows]


@router.post("/", response_model=IncomeOut, status_code=201)
async def create_income(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: IncomeCreate,
) -> IncomeOut:
    freq = _parse_frequency(body.frequency)
    tax = _parse_taxability(body.taxability)
    iid = await income_repo.insert_income_source(
        conn,
        name=body.name,
        type_=body.type,
        amount_paise=body.amount_paise,
        frequency=freq.value,
        taxability=tax.value,
        is_active=body.is_active,
        default_account_id=body.default_account_id,
        category=body.category,
    )
    row = await income_repo.get_income_source(conn, iid)
    if row is None:
        raise HTTPException(status_code=500, detail="income stream not found after insert")
    return _to_out(row)


@router.get("/{income_id}", response_model=IncomeOut)
async def get_income(
    income_id: int,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> IncomeOut:
    row = await income_repo.get_income_source(conn, income_id)
    if row is None:
        raise HTTPException(status_code=404, detail="income stream not found")
    return _to_out(row)


@router.put("/{income_id}", response_model=IncomeOut)
async def put_income(
    income_id: int,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: IncomePut,
) -> IncomeOut:
    existing = await income_repo.get_income_source(conn, income_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="income stream not found")
    freq = _parse_frequency(body.frequency)
    tax = _parse_taxability(body.taxability)
    await income_repo.update_income_source(
        conn,
        income_id=income_id,
        name=body.name,
        type_=body.type,
        amount_paise=body.amount_paise,
        frequency=freq.value,
        taxability=tax.value,
        is_active=body.is_active,
        default_account_id=body.default_account_id,
        category=body.category,
    )
    row = await income_repo.get_income_source(conn, income_id)
    if row is None:
        raise HTTPException(status_code=500, detail="income stream not found after update")
    return _to_out(row)


@router.delete("/{income_id}", status_code=204)
async def delete_income(
    income_id: int,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> None:
    ok = await income_repo.delete_income_source(conn, income_id)
    if not ok:
        raise HTTPException(status_code=404, detail="income stream not found")


@router.post(
    "/{income_id}/record-income",
    response_model=RecordIncomeOut,
    status_code=201,
)
async def record_income(
    income_id: int,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    request: Request,
    body: RecordIncomeBody,
) -> RecordIncomeOut:
    """Post one income credit through the ledger from a planning stream."""
    row = await income_repo.get_income_source(conn, income_id)
    if row is None:
        raise HTTPException(status_code=404, detail="income stream not found")

    project_config = await load_project_config(conn)
    if project_config.ledger_engine != "double_entry":
        raise HTTPException(
            status_code=422,
            detail="record-income requires double_entry ledger engine",
        )

    payment_account_id = body.account_id or row.default_account_id
    if payment_account_id is None:
        raise HTTPException(
            status_code=422,
            detail="account_id required (on income stream or in request body)",
        )
    if await accounts_repo.get_account(conn, payment_account_id) is None:
        raise HTTPException(status_code=404, detail="account_id not found")

    try:
        date_cls.fromisoformat(body.date)
    except ValueError as e:
        raise HTTPException(status_code=422, detail="invalid date") from e

    require_ledger_writes(request)
    try:
        ledger_transaction_id, updated = await post_income_credit(
            conn,
            source=row,
            payment_date=body.date,
            amount_paise=body.amount_paise,
            account_id=body.account_id,
            category=body.category,
        )
    except LedgerError as exc:
        detail = str(exc)
        if "does not exist" in detail:
            raise HTTPException(status_code=409, detail=detail) from exc
        raise HTTPException(status_code=422, detail=detail) from exc

    return RecordIncomeOut(
        ledger_transaction_id=ledger_transaction_id,
        income=_to_out(updated),
    )
