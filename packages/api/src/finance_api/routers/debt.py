"""Debt / loans API."""

from __future__ import annotations

from dataclasses import replace
from datetime import date as date_cls
from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Request

from finance_api.deps import get_conn
from finance_api.deps_ledger import require_ledger_writes
from finance_api.schemas.debt import (
    AmortizationResponse,
    DebtCreateBody,
    DebtOut,
    DebtPutBody,
    DebtSummaryOut,
    LoanDisbursalBody,
    LoanDisbursalOut,
    RecordEmiBody,
    RecordEmiOut,
)
from finance_api.services.amortization import (
    build_phased_schedule,
    build_schedule,
    compute_emi_advance,
)
from finance_api.services.debt_emi import (
    auto_advance_active_debts,
    auto_advance_debt,
    post_emi_and_advance,
    resolve_active_debt_totals,
    resolve_debt_outstanding,
)
from finance_common.ledger.errors import LedgerError
from finance_common.project_config import load_project_config
from finance_common.repositories import accounts as accounts_repo
from finance_common.repositories import debts as debt_repo
from finance_common.repositories.debts import DebtRow

router = APIRouter(prefix="/debt", tags=["debt"])


def _to_out(row: DebtRow, *, outstanding_paise: int | None = None) -> DebtOut:
    balance = (
        row.current_balance_paise if outstanding_paise is None else outstanding_paise
    )
    return DebtOut(
        id=row.id,
        name=row.name,
        lender=row.lender,
        type=row.type,
        original_amount_paise=row.original_amount_paise,
        current_balance_paise=balance,
        emi_paise=row.emi_paise,
        rate_percent=row.rate_percent,
        start_date=row.start_date,
        next_emi_date=row.next_emi_date,
        status=row.status,
        tenure_months=row.tenure_months,
        first_emi_date=row.first_emi_date,
        full_emi_start_date=row.full_emi_start_date,
        account_id=row.account_id,
        payment_account_id=row.payment_account_id,
    )


async def _to_out_live(conn: aiosqlite.Connection, row: DebtRow) -> DebtOut:
    return _to_out(row, outstanding_paise=await resolve_debt_outstanding(conn, row))


def _merge_row(existing: DebtRow, body: DebtPutBody) -> DebtRow:
    patch = body.model_dump(exclude_unset=True)
    return replace(existing, **patch)


async def _ensure_loan_account(
    conn: aiosqlite.Connection,
    *,
    debt_name: str,
    lender: str | None,
    existing_account_id: int | None,
) -> int:
    if existing_account_id is not None:
        return existing_account_id
    return await accounts_repo.create_account(
        conn,
        name=debt_name.strip(),
        type="loan",
        institution=lender.strip() if lender else None,
    )


async def _validate_payment_account(
    conn: aiosqlite.Connection, payment_account_id: int | None
) -> None:
    if payment_account_id is None:
        return
    if await accounts_repo.get_account(conn, payment_account_id) is None:
        raise HTTPException(status_code=404, detail="payment_account_id not found")


@router.get("/", response_model=list[DebtOut])
async def list_debts(conn: Annotated[aiosqlite.Connection, Depends(get_conn)]) -> list[DebtOut]:
    await auto_advance_active_debts(conn)
    rows = await debt_repo.list_debts(conn)
    return [await _to_out_live(conn, r) for r in rows]


@router.post("/", response_model=DebtOut, status_code=201)
async def create_debt(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: DebtCreateBody,
) -> DebtOut:
    project_config = await load_project_config(conn)
    account_id: int | None = None
    if project_config.ledger_engine == "double_entry":
        await _validate_payment_account(conn, body.payment_account_id)
        account_id = await _ensure_loan_account(
            conn,
            debt_name=body.name,
            lender=body.lender,
            existing_account_id=None,
        )

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
        account_id=account_id,
        payment_account_id=body.payment_account_id,
    )
    row = await debt_repo.get_debt(conn, did)
    if row is None:
        raise HTTPException(status_code=500, detail="debt not found after insert")
    return await _to_out_live(conn, row)


@router.get("/summary", response_model=DebtSummaryOut)
async def debt_summary(conn: Annotated[aiosqlite.Connection, Depends(get_conn)]) -> DebtSummaryOut:
    await auto_advance_active_debts(conn)
    tot, emi, n = await resolve_active_debt_totals(conn)
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
    advanced = await auto_advance_debt(conn, row)
    row = advanced if advanced is not None else row
    return await _to_out_live(conn, row)


@router.put("/{debt_id}", response_model=DebtOut)
async def put_debt(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    debt_id: int,
    body: DebtPutBody,
) -> DebtOut:
    existing = await debt_repo.get_debt(conn, debt_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Debt not found")
    await _validate_payment_account(conn, body.payment_account_id)
    merged = _merge_row(existing, body)
    project_config = await load_project_config(conn)
    if project_config.ledger_engine == "double_entry" and merged.account_id is None:
        merged = replace(
            merged,
            account_id=await _ensure_loan_account(
                conn,
                debt_name=merged.name,
                lender=merged.lender,
                existing_account_id=None,
            ),
        )
    await debt_repo.update_debt_row(conn, merged)
    return await _to_out_live(conn, merged)


@router.delete("/{debt_id}", status_code=204)
async def delete_debt(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    debt_id: int,
) -> None:
    ok = await debt_repo.delete_debt(conn, debt_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Debt not found")


@router.post("/{debt_id}/record-emi", response_model=RecordEmiOut, status_code=201)
async def record_emi(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    request: Request,
    debt_id: int,
    body: RecordEmiBody,
) -> RecordEmiOut:
    """Post one EMI payment through the ledger (principal + interest split)."""
    row = await debt_repo.get_debt(conn, debt_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Debt not found")

    project_config = await load_project_config(conn)
    if project_config.ledger_engine != "double_entry":
        raise HTTPException(
            status_code=409,
            detail="record-emi requires double_entry ledger engine",
        )
    if row.account_id is None:
        raise HTTPException(
            status_code=409,
            detail="No linked loan account — update debt or recreate in double_entry mode",
        )

    payment_account_id = body.payment_account_id or row.payment_account_id
    if payment_account_id is None:
        raise HTTPException(
            status_code=422,
            detail="payment_account_id required (on debt or in request body)",
        )
    if await accounts_repo.get_account(conn, payment_account_id) is None:
        raise HTTPException(status_code=404, detail="payment_account_id not found")
    if await accounts_repo.get_account(conn, row.account_id) is None:
        raise HTTPException(status_code=404, detail="loan account not found")

    try:
        tx_date = date_cls.fromisoformat(body.date)
    except ValueError as e:
        raise HTTPException(status_code=422, detail="invalid date") from e

    require_ledger_writes(request)
    try:
        ledger_transaction_id, _ = await post_emi_and_advance(
            conn,
            row,
            tx_date=tx_date,
            principal_paise=body.principal_paise,
            interest_paise=body.interest_paise,
            payment_account_id=payment_account_id,
            source="dashboard",
        )
    except LedgerError as exc:
        detail = str(exc)
        if "does not exist" in detail:
            raise HTTPException(status_code=409, detail=detail) from exc
        raise HTTPException(status_code=422, detail=detail) from exc

    return RecordEmiOut(ledger_transaction_id=ledger_transaction_id)


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

    # Also advance next_emi_date and mark paid if done
    result = compute_emi_advance(row)
    if result:
        new_bal, new_next_date, new_status = result
        updated = replace(
            row,
            current_balance_paise=new_bal,
            next_emi_date=new_next_date,
            status=new_status,
        )
    else:
        updated = replace(row, current_balance_paise=estimated_balance)
    await debt_repo.update_debt_row(conn, updated)
    return await _to_out_live(conn, updated)


@router.post("/sync-all-balances", response_model=list[DebtOut])
async def sync_all_balances(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> list[DebtOut]:
    """
    Run EMI auto-advance for every active debt with an overdue EMI.
    Updates current_balance_paise, next_emi_date, and status for each eligible debt.
    """
    await auto_advance_active_debts(conn)
    debts = await debt_repo.list_debts(conn, status="active")
    return [await _to_out_live(conn, d) for d in debts]
