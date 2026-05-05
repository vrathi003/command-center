"""Debt / loans API."""

from __future__ import annotations

from dataclasses import replace
from datetime import date as date_cls
from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from finance_api.deps import get_conn
from finance_api.schemas.debt import (
    AmortizationResponse,
    DebtCreateBody,
    DebtOut,
    DebtPutBody,
    DebtSummaryOut,
    LoanDisbursalBody,
    LoanDisbursalOut,
)
from finance_api.services.amortization import build_phased_schedule, build_schedule
from finance_common.repositories import debts as debt_repo
from finance_common.repositories.debts import DebtRow

router = APIRouter(prefix="/debt", tags=["debt"])


def _to_out(row: DebtRow) -> DebtOut:
    return DebtOut(
        id=row.id,
        name=row.name,
        lender=row.lender,
        type=row.type,
        original_amount_paise=row.original_amount_paise,
        current_balance_paise=row.current_balance_paise,
        emi_paise=row.emi_paise,
        rate_percent=row.rate_percent,
        start_date=row.start_date,
        next_emi_date=row.next_emi_date,
        status=row.status,
        tenure_months=row.tenure_months,
        first_emi_date=row.first_emi_date,
        full_emi_start_date=row.full_emi_start_date,
    )


def _merge_row(existing: DebtRow, body: DebtPutBody) -> DebtRow:
    patch = body.model_dump(exclude_unset=True)
    return replace(existing, **patch)


@router.get("/", response_model=list[DebtOut])
async def list_debts(conn: Annotated[aiosqlite.Connection, Depends(get_conn)]) -> list[DebtOut]:
    rows = await debt_repo.list_debts(conn)
    return [_to_out(r) for r in rows]


@router.post("/", response_model=DebtOut, status_code=201)
async def create_debt(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: DebtCreateBody,
) -> DebtOut:
    did = await debt_repo.insert_debt(
        conn,
        name=body.name,
        lender=body.lender,
        type_=body.type,
        original_amount_paise=body.original_amount_paise,
        current_balance_paise=body.current_balance_paise,
        emi_paise=body.emi_paise,
        rate_percent=body.rate_percent,
        start_date=body.start_date,
        next_emi_date=body.next_emi_date,
        status=body.status,
        tenure_months=body.tenure_months,
        first_emi_date=body.first_emi_date,
        full_emi_start_date=body.full_emi_start_date,
    )
    row = await debt_repo.get_debt(conn, did)
    if row is None:
        raise HTTPException(status_code=500, detail="debt not found after insert")
    return _to_out(row)


@router.get("/summary", response_model=DebtSummaryOut)
async def debt_summary(conn: Annotated[aiosqlite.Connection, Depends(get_conn)]) -> DebtSummaryOut:
    tot, emi, n = await debt_repo.aggregate_active(conn)
    nd, nn = await debt_repo.next_emi_hint(conn)
    return DebtSummaryOut(
        total_outstanding_paise=tot,
        total_emi_monthly_paise=emi,
        active_count=n,
        next_emi_date=nd,
        next_emi_debt_name=nn,
    )


@router.get("/{debt_id}/amortization", response_model=AmortizationResponse)
async def get_amortization(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    debt_id: int,
) -> AmortizationResponse:
    row = await debt_repo.get_debt(conn, debt_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Debt not found")

    disbursals = await debt_repo.list_disbursals(conn, debt_id)

    # ── Phased mode: home loan with disbursal schedule ────────────────────────
    if (
        disbursals
        and row.start_date
        and row.rate_percent
        and row.emi_paise
        and row.tenure_months
    ):
        full_emi_start = row.full_emi_start_date or max(d.disbursal_date for d in disbursals)
        total_disbursed = sum(d.amount_paise for d in disbursals)
        rows, payoff = build_phased_schedule(
            disbursals=[(d.disbursal_date, d.amount_paise) for d in disbursals],
            annual_rate_percent=row.rate_percent,
            emi_paise=row.emi_paise,
            full_emi_start_date=full_emi_start,
            tenure_months=row.tenure_months,
            loan_start_date=row.start_date,
        )
        pre_emi_count = sum(1 for r in rows if r.phase == "pre_emi")
        return AmortizationResponse(
            debt_id=debt_id,
            rows=rows,
            payoff_months=payoff,
            is_phased=True,
            total_pre_emi_months=pre_emi_count,
            total_disbursed_paise=total_disbursed,
        )

    # ── Simple mode ───────────────────────────────────────────────────────────
    principal = row.original_amount_paise or row.current_balance_paise
    rows, payoff = build_schedule(
        principal,
        row.rate_percent,
        row.emi_paise,
        tenure_months=row.tenure_months,
    )
    return AmortizationResponse(
        debt_id=debt_id,
        rows=rows,
        payoff_months=payoff,
        is_phased=False,
    )


@router.get("/{debt_id}", response_model=DebtOut)
async def get_debt(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    debt_id: int,
) -> DebtOut:
    row = await debt_repo.get_debt(conn, debt_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Debt not found")
    return _to_out(row)


@router.put("/{debt_id}", response_model=DebtOut)
async def put_debt(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    debt_id: int,
    body: DebtPutBody,
) -> DebtOut:
    existing = await debt_repo.get_debt(conn, debt_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Debt not found")
    merged = _merge_row(existing, body)
    await debt_repo.update_debt_row(conn, merged)
    return _to_out(merged)


@router.delete("/{debt_id}", status_code=204)
async def delete_debt(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    debt_id: int,
) -> None:
    ok = await debt_repo.delete_debt(conn, debt_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Debt not found")


# ── Disbursal endpoints ───────────────────────────────────────────────────────

@router.get("/{debt_id}/disbursals", response_model=list[LoanDisbursalOut])
async def list_disbursals(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    debt_id: int,
) -> list[LoanDisbursalOut]:
    if await debt_repo.get_debt(conn, debt_id) is None:
        raise HTTPException(status_code=404, detail="Debt not found")
    disbursals = await debt_repo.list_disbursals(conn, debt_id)
    cumulative = 0
    result = []
    for d in disbursals:
        cumulative += d.amount_paise
        result.append(LoanDisbursalOut(
            id=d.id,
            debt_id=d.debt_id,
            disbursal_date=d.disbursal_date,
            amount_paise=d.amount_paise,
            cumulative_paise=cumulative,
            notes=d.notes,
            created_at=d.created_at,
        ))
    return result


@router.post("/{debt_id}/disbursals", response_model=LoanDisbursalOut, status_code=201)
async def add_disbursal(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    debt_id: int,
    body: LoanDisbursalBody,
) -> LoanDisbursalOut:
    if await debt_repo.get_debt(conn, debt_id) is None:
        raise HTTPException(status_code=404, detail="Debt not found")

    new_id = await debt_repo.insert_disbursal(
        conn,
        debt_id=debt_id,
        disbursal_date=body.disbursal_date,
        amount_paise=body.amount_paise,
        notes=body.notes,
    )
    all_d = await debt_repo.list_disbursals(conn, debt_id)
    cumulative = 0
    for d in all_d:
        cumulative += d.amount_paise
        if d.id == new_id:
            return LoanDisbursalOut(
                id=d.id,
                debt_id=d.debt_id,
                disbursal_date=d.disbursal_date,
                amount_paise=d.amount_paise,
                cumulative_paise=cumulative,
                notes=d.notes,
                created_at=d.created_at,
            )
    raise HTTPException(status_code=500, detail="Disbursal not found after insert")


@router.delete("/{debt_id}/disbursals/{disbursal_id}", status_code=204)
async def delete_disbursal(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    debt_id: int,
    disbursal_id: int,
) -> None:
    ok = await debt_repo.delete_disbursal(conn, disbursal_id, debt_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Disbursal not found")


# ── Balance sync ──────────────────────────────────────────────────────────────

@router.post("/{debt_id}/sync-balance", response_model=DebtOut)
async def sync_balance_from_schedule(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    debt_id: int,
) -> DebtOut:
    """
    Re-estimate current_balance_paise from the amortization schedule using
    months elapsed since first_emi_date (or start_date).
    """
    row = await debt_repo.get_debt(conn, debt_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Debt not found")

    ref_date_str = row.first_emi_date or row.start_date
    if not ref_date_str:
        raise HTTPException(
            status_code=422,
            detail="Set first_emi_date or start_date before syncing balance.",
        )

    ref_date = date_cls.fromisoformat(ref_date_str[:10])
    today = date_cls.today()
    emis_paid = max(
        0,
        (today.year - ref_date.year) * 12 + (today.month - ref_date.month),
    )

    disbursals = await debt_repo.list_disbursals(conn, debt_id)
    if (
        disbursals
        and row.start_date
        and row.rate_percent
        and row.emi_paise
        and row.tenure_months
    ):
        full_emi_start = row.full_emi_start_date or max(d.disbursal_date for d in disbursals)
        sched_rows, _ = build_phased_schedule(
            disbursals=[(d.disbursal_date, d.amount_paise) for d in disbursals],
            annual_rate_percent=row.rate_percent,
            emi_paise=row.emi_paise,
            full_emi_start_date=full_emi_start,
            tenure_months=row.tenure_months,
            loan_start_date=row.start_date,
        )
    else:
        principal = row.original_amount_paise or row.current_balance_paise
        sched_rows, _ = build_schedule(
            principal,
            row.rate_percent,
            row.emi_paise,
            tenure_months=row.tenure_months,
        )

    if not sched_rows:
        raise HTTPException(
            status_code=422,
            detail="Cannot build schedule — check rate/EMI/tenure.",
        )

    idx = min(emis_paid, len(sched_rows)) - 1
    estimated_balance = (
        sched_rows[idx].balance_after_paise
        if idx >= 0
        else (row.original_amount_paise or row.current_balance_paise)
    )

    updated = replace(row, current_balance_paise=estimated_balance)
    await debt_repo.update_debt_row(conn, updated)
    return _to_out(updated)
