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
    advance_months,
    build_phased_schedule,
    build_schedule,
    compute_emi_advance,
    emis_due_count,
)
from finance_api.services.debt_emi import auto_advance_active_debts, auto_advance_debt
from finance_common.ledger import builders
from finance_common.ledger import service as ledger_service
from finance_common.ledger.balances import account_balance_paise
from finance_common.ledger.errors import LedgerError
from finance_common.ledger.models import PostTransactionInput
from finance_common.project_config import load_project_config
from finance_common.repositories import accounts as accounts_repo
from finance_common.repositories import debts as debt_repo
from finance_common.repositories.debts import DebtRow

router = APIRouter(prefix="/debt", tags=["debt"])

_UNCATEGORIZED_EXPENSE = "Uncategorized Expense"


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
        account_id=row.account_id,
        payment_account_id=row.payment_account_id,
    )


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


async def _uncategorized_expense_id(conn: aiosqlite.Connection) -> int:
    account = await accounts_repo.get_account_by_name(conn, _UNCATEGORIZED_EXPENSE)
    if account is None:
        raise HTTPException(
            status_code=409,
            detail=f"Required system account {_UNCATEGORIZED_EXPENSE!r} does not exist",
        )
    return account.id


async def _loan_outstanding_paise(conn: aiosqlite.Connection, account_id: int) -> int:
    balance = await account_balance_paise(conn, account_id)
    return max(0, -balance)


def _schedule_rows(debt: DebtRow) -> list:
    principal = debt.original_amount_paise or debt.current_balance_paise
    rows, _ = build_schedule(
        principal,
        debt.rate_percent,
        debt.emi_paise,
        tenure_months=debt.tenure_months,
    )
    return rows


def _default_emi_split(debt: DebtRow, tx_date: date_cls) -> tuple[int, int]:
    schedule_ref = debt.first_emi_date or debt.start_date
    if not schedule_ref:
        emi = debt.emi_paise or 0
        return emi, 0

    ref = date_cls.fromisoformat(schedule_ref[:10])
    if debt.next_emi_date:
        payment_num = emis_due_count(ref, date_cls.fromisoformat(debt.next_emi_date[:10]))
    else:
        payment_num = emis_due_count(ref, tx_date)

    sched = _schedule_rows(debt)
    if not sched or payment_num < 1 or payment_num > len(sched):
        emi = debt.emi_paise or 0
        return emi, 0

    row = sched[payment_num - 1]
    return row.principal_paise, row.interest_paise


def _advance_after_one_emi(debt: DebtRow) -> tuple[str | None, str]:
    if debt.next_emi_date:
        due = date_cls.fromisoformat(debt.next_emi_date[:10])
        new_next = advance_months(due, 1).isoformat()
    elif debt.first_emi_date or debt.start_date:
        ref = date_cls.fromisoformat((debt.first_emi_date or debt.start_date)[:10])
        new_next = advance_months(ref, 1).isoformat()
    else:
        new_next = debt.next_emi_date

    new_status = "closed" if debt.current_balance_paise == 0 else "active"
    return new_next, new_status


@router.get("/", response_model=list[DebtOut])
async def list_debts(conn: Annotated[aiosqlite.Connection, Depends(get_conn)]) -> list[DebtOut]:
    await auto_advance_active_debts(conn)
    rows = await debt_repo.list_debts(conn)
    return [_to_out(r) for r in rows]


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
    return _to_out(row)


@router.get("/summary", response_model=DebtSummaryOut)
async def debt_summary(conn: Annotated[aiosqlite.Connection, Depends(get_conn)]) -> DebtSummaryOut:
    await auto_advance_active_debts(conn)
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
    advanced = await auto_advance_debt(conn, row)
    row = advanced if advanced is not None else row
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
    return _to_out(merged)


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

    principal_paise = body.principal_paise
    interest_paise = body.interest_paise
    if principal_paise is None or interest_paise is None:
        default_principal, default_interest = _default_emi_split(row, tx_date)
        principal_paise = default_principal if principal_paise is None else principal_paise
        interest_paise = default_interest if interest_paise is None else interest_paise

    total = principal_paise + interest_paise
    if total <= 0:
        raise HTTPException(status_code=422, detail="EMI total must be positive")

    require_ledger_writes(request)
    expense_account_id = await _uncategorized_expense_id(conn)
    try:
        ledger_transaction_id = await ledger_service.post(
            conn,
            PostTransactionInput(
                tx_date=tx_date,
                postings=builders.build_emi_payment(
                    bank_id=payment_account_id,
                    loan_id=row.account_id,
                    expense_account_id=expense_account_id,
                    principal_paise=principal_paise,
                    interest_paise=interest_paise,
                ),
                payee=row.name,
                notes=f"EMI payment · {row.name}",
                source="dashboard",
                external_key=f"debt_emi:{debt_id}:{body.date}:{total}",
            ),
        )
    except LedgerError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    outstanding = await _loan_outstanding_paise(conn, row.account_id)
    new_next, new_status = _advance_after_one_emi(
        replace(row, current_balance_paise=outstanding)
    )
    updated = replace(
        row,
        current_balance_paise=outstanding,
        next_emi_date=new_next,
        status=new_status,
        payment_account_id=payment_account_id,
    )
    await debt_repo.update_debt_row(conn, updated)
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
    return _to_out(updated)


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
    return [_to_out(d) for d in debts]
