"""Credit cards and statement uploads."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from finance_api.deps import get_conn, get_settings
from finance_api.schemas.credit_card import (
    CreditCardCreateBody,
    CreditCardEmiCreateBody,
    CreditCardEmiOut,
    CreditCardEmiPutBody,
    CreditCardOut,
    CreditCardPutBody,
    CreditCardStatementApplyResponse,
    CreditCardStatementOut,
    LiveBalanceResponse,
    PayBillBody,
)
from finance_api.schemas.debt import DebtOut
from finance_api.services.credit_card_statement_service import (
    build_credit_card_statement_payload,
    dumps_line_items,
    dumps_summary,
)
from finance_api.settings import ApiSettings
from finance_common.fy import current_fy_from_date, fy_start
from finance_common.parsing.credit_card_statement import (
    infer_cc_payment_mode,
    line_items_json_loads,
    summary_json_loads,
)
from finance_common.parsing.transaction_import import parse_transaction_date
from finance_common.repositories import accounts as accounts_repo
from finance_common.repositories import credit_cards as cc_repo
from finance_common.repositories import debts as debt_repo
from finance_common.repositories import transactions as tx_repo
from finance_common.repositories.credit_cards import (
    CreditCardEmiRow,
    CreditCardRow,
    CreditCardStatementRow,
)
from finance_common.types import Category, Paise, PaymentMode

router = APIRouter(prefix="/credit-cards", tags=["credit-cards"])


def _total_limit_used(bal: int | None, emi_blocked: int) -> int:
    return (bal or 0) + emi_blocked


def _util_pct(limit: int, total_used: int) -> float | None:
    if limit <= 0:
        return None
    return round(min(100.0, (total_used / limit) * 100.0), 2)


def _card_out(
    row: CreditCardRow,
    emi: tuple[int, int, int] = (0, 0, 0),
    live_balance: int | None = None,
) -> CreditCardOut:
    blocked, monthly, count = emi
    total = _total_limit_used(row.current_balance_paise, blocked)
    return CreditCardOut(
        id=row.id,
        name=row.name,
        issuer=row.issuer,
        last_four=row.last_four,
        credit_limit_paise=row.credit_limit_paise,
        current_balance_paise=row.current_balance_paise,
        notes=row.notes,
        is_active=row.is_active,
        utilization_pct=_util_pct(row.credit_limit_paise, total),
        emi_limit_blocked_paise=blocked,
        emi_monthly_due_paise=monthly,
        emi_active_plan_count=count,
        total_limit_used_paise=total,
        account_id=row.account_id,
        statement_day=row.statement_day,
        due_day=row.due_day,
        minimum_due_pct=row.minimum_due_pct,
        reward_rate_pct=row.reward_rate_pct,
        live_balance_paise=live_balance,
    )


def _emi_principal_basis(row: CreditCardEmiRow) -> int:
    if row.principal_paise is not None:
        return row.principal_paise
    return row.limit_blocked_paise


def _emi_opt_str(s: str | None) -> str | None:
    if s is None:
        return None
    t = s.strip()
    return t if t else None


def _emi_out(row: CreditCardEmiRow) -> CreditCardEmiOut:
    rem = max(0, row.tenure_months - row.installments_paid) if row.is_active else 0
    principal_basis = _emi_principal_basis(row)
    monthly = row.emi_amount_paise
    tenure = row.tenure_months
    paid = row.installments_paid
    total_schedule = monthly * tenure
    total_interest = max(0, total_schedule - principal_basis)
    interest_pct = (
        round((total_interest / principal_basis) * 100.0, 2) if principal_basis > 0 else None
    )
    amount_paid_to_date = monthly * paid
    interest_paid_est = int(round(total_interest * (paid / tenure))) if tenure > 0 else 0
    interest_remaining_est = max(0, total_interest - interest_paid_est)
    return CreditCardEmiOut(
        id=row.id,
        credit_card_id=row.credit_card_id,
        description=row.description,
        limit_blocked_paise=row.limit_blocked_paise,
        emi_amount_paise=row.emi_amount_paise,
        tenure_months=row.tenure_months,
        installments_paid=row.installments_paid,
        is_active=row.is_active,
        notes=row.notes,
        loan_type=row.loan_type,
        creation_date=row.creation_date,
        finish_date=row.finish_date,
        principal_paise=row.principal_paise,
        outstanding_instalment_paise=row.outstanding_instalment_paise,
        installments_remaining=rem,
        pending_installments=rem,
        principal_basis_paise=principal_basis,
        total_repayment_schedule_paise=total_schedule,
        total_interest_estimated_paise=total_interest,
        interest_over_principal_pct=interest_pct,
        amount_paid_to_date_paise=amount_paid_to_date,
        interest_paid_estimated_paise=interest_paid_est,
        interest_remaining_estimated_paise=interest_remaining_est,
    )


def _merge_emi(existing: CreditCardEmiRow, body: CreditCardEmiPutBody) -> CreditCardEmiRow:
    patch = body.model_dump(exclude_unset=True)
    if not patch:
        return existing
    for k in ("loan_type", "creation_date", "finish_date"):
        if k in patch:
            v = patch[k]
            if v is None:
                continue
            s = str(v).strip()
            patch[k] = s if s else None
    return replace(existing, **patch)


def _stmt_out(row: CreditCardStatementRow) -> CreditCardStatementOut:
    return CreditCardStatementOut(
        id=row.id,
        credit_card_id=row.credit_card_id,
        filename=row.filename,
        period_start=row.period_start,
        period_end=row.period_end,
        extraction_preview=row.extraction_preview,
        summary=summary_json_loads(row.summary_json),
        line_items=line_items_json_loads(row.line_items_json),
        status=row.status,
        created_at=row.created_at,
    )


def _merge_card(existing: CreditCardRow, body: CreditCardPutBody) -> CreditCardRow:
    patch = body.model_dump(exclude_unset=True)
    if not patch:
        return existing
    return replace(existing, **patch)


@router.get("/", response_model=list[CreditCardOut])
async def list_cards(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    active_only: Annotated[bool, Query()] = False,
) -> list[CreditCardOut]:
    totals = await cc_repo.emi_totals_by_card(conn)
    rows = await cc_repo.list_credit_cards(conn, active_only=active_only)
    linked_ids = [r.account_id for r in rows if r.account_id is not None]
    live_bals = await tx_repo.cc_live_balances_batch(conn, linked_ids)
    return [
        _card_out(r, totals.get(r.id, (0, 0, 0)), live_bals.get(r.account_id) if r.account_id else None)  # noqa: E501
        for r in rows
    ]


@router.post("/", response_model=CreditCardOut, status_code=201)
async def create_card(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    body: CreditCardCreateBody,
) -> CreditCardOut:
    card_name = body.name.strip()
    linked_account_id = body.account_id
    if linked_account_id is None:
        linked_account_id = await accounts_repo.create_account(
            conn,
            name=card_name,
            type="credit_card",
            institution=body.issuer.strip() if body.issuer else None,
        )
    cid = await cc_repo.insert_credit_card(
        conn,
        name=card_name,
        issuer=body.issuer.strip() if body.issuer else None,
        last_four=body.last_four.strip() if body.last_four else None,
        credit_limit_paise=body.credit_limit_paise,
        current_balance_paise=body.current_balance_paise,
        notes=body.notes.strip() if body.notes else None,
        is_active=body.is_active,
        account_id=linked_account_id,
        statement_day=body.statement_day,
        due_day=body.due_day,
        minimum_due_pct=body.minimum_due_pct,
        reward_rate_pct=body.reward_rate_pct,
    )
    row = await cc_repo.get_credit_card(conn, cid)
    if row is None:
        raise HTTPException(status_code=500, detail="card not found after insert")
    return _card_out(row, (0, 0, 0))


@router.get("/{card_id}", response_model=CreditCardOut)
async def get_card(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    card_id: int,
) -> CreditCardOut:
    row = await cc_repo.get_credit_card(conn, card_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Credit card not found")
    totals = await cc_repo.emi_totals_by_card(conn)
    live_bal: int | None = None
    if row.account_id is not None:
        live_bal = await tx_repo.cc_live_balance(conn, row.account_id)
    return _card_out(row, totals.get(card_id, (0, 0, 0)), live_bal)


@router.put("/{card_id}", response_model=CreditCardOut)
async def put_card(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    card_id: int,
    body: CreditCardPutBody,
) -> CreditCardOut:
    existing = await cc_repo.get_credit_card(conn, card_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Credit card not found")
    merged = _merge_card(existing, body)
    await cc_repo.update_credit_card_row(conn, merged)
    # Sync name change to the linked accounts entry
    name_changed = body.name is not None and body.name.strip() != existing.name
    if name_changed and existing.account_id is not None:
        acc = await accounts_repo.get_account(conn, existing.account_id)
        if acc is not None:
            await accounts_repo.update_account(
                conn,
                existing.account_id,
                name=merged.name,
                type=acc.type,
                institution=acc.institution,
                currency=acc.currency,
                is_active=acc.is_active,
            )
    totals = await cc_repo.emi_totals_by_card(conn)
    return _card_out(merged, totals.get(card_id, (0, 0, 0)))


@router.delete("/{card_id}", status_code=204)
async def delete_card(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    card_id: int,
) -> None:
    ok = await cc_repo.delete_credit_card(conn, card_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Credit card not found")


@router.post("/{card_id}/link-account", response_model=CreditCardOut)
async def link_account(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    card_id: int,
) -> CreditCardOut:
    """Create a linked account for an existing card that has none.

    Idempotent — if the card already has an account_id, returns the card as-is.
    """
    card = await cc_repo.get_credit_card(conn, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Credit card not found")
    if card.account_id is not None:
        totals = await cc_repo.emi_totals_by_card(conn)
        live_bal = await tx_repo.cc_live_balance(conn, card.account_id)
        return _card_out(card, totals.get(card_id, (0, 0, 0)), live_bal)
    new_account_id = await accounts_repo.create_account(
        conn,
        name=card.name,
        type="credit_card",
        institution=card.issuer,
    )
    await cc_repo.set_account_id(conn, card_id, new_account_id)
    row = await cc_repo.get_credit_card(conn, card_id)
    if row is None:
        raise HTTPException(status_code=500, detail="card not found after update")
    totals = await cc_repo.emi_totals_by_card(conn)
    return _card_out(row, totals.get(card_id, (0, 0, 0)), 0)


@router.get("/{card_id}/interest-leakage")
async def get_interest_leakage(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    card_id: int,
) -> dict[str, int]:
    """Total interest + fees paid on this card — all-time and current FY."""
    card = await cc_repo.get_credit_card(conn, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Credit card not found")
    if card.account_id is None:
        return {"all_time_paise": 0, "fy_paise": 0}
    fy = current_fy_from_date()
    fy_s = fy_start(fy).isoformat()
    return await tx_repo.cc_interest_leakage(conn, card.account_id, fy_start=fy_s)


@router.get("/{card_id}/live-balance", response_model=LiveBalanceResponse)
async def get_live_balance(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    card_id: int,
) -> LiveBalanceResponse:
    """Compute live CC outstanding from transaction history on the linked account."""
    card = await cc_repo.get_credit_card(conn, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Credit card not found")
    if card.account_id is None:
        raise HTTPException(
            status_code=409,
            detail="No linked account — create a new card to auto-link or set account_id",
        )
    balance = await tx_repo.cc_live_balance(conn, card.account_id)
    return LiveBalanceResponse(live_balance_paise=balance, account_id=card.account_id)


@router.post("/{card_id}/pay-bill", response_model=dict, status_code=201)
async def pay_bill(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    card_id: int,
    body: PayBillBody,
) -> dict:
    """Record a CC bill payment as a transfer from bank account to the CC's linked account."""
    card = await cc_repo.get_credit_card(conn, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Credit card not found")
    if card.account_id is None:
        raise HTTPException(
            status_code=409,
            detail="No linked account on this card — cannot record bill payment",
        )
    if body.from_account_id == card.account_id:
        raise HTTPException(
            status_code=400,
            detail="from_account_id cannot be the same as the CC linked account",
        )
    try:
        tx_date = date.fromisoformat(body.date)
    except ValueError as e:
        raise HTTPException(status_code=422, detail="invalid date") from e
    from_acc = await accounts_repo.get_account(conn, body.from_account_id)
    if from_acc is None:
        raise HTTPException(status_code=404, detail="from_account_id not found")
    cc_acc = await accounts_repo.get_account(conn, card.account_id)
    if cc_acc is None:
        raise HTTPException(status_code=404, detail="CC linked account not found")
    out_id, in_id, pair_id = await tx_repo.insert_transfer_pair(
        conn,
        amount_paise=Paise(body.amount_paise),
        tx_date=tx_date,
        from_account_id=body.from_account_id,
        to_account_id=card.account_id,
        from_account_name=from_acc.name,
        to_account_name=cc_acc.name,
        notes=body.notes or f"CC bill payment · {card.name}",
        source="dashboard",
    )
    return {
        "transfer_pair_id": pair_id,
        "debit_transaction_id": out_id,
        "credit_transaction_id": in_id,
    }


@router.get("/{card_id}/statements", response_model=list[CreditCardStatementOut])
async def list_statements(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    card_id: int,
) -> list[CreditCardStatementOut]:
    row = await cc_repo.get_credit_card(conn, card_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Credit card not found")
    stmts = await cc_repo.list_statements_for_card(conn, card_id)
    return [_stmt_out(s) for s in stmts]


@router.get("/{card_id}/statements/{statement_id}", response_model=CreditCardStatementOut)
async def get_statement_detail(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    card_id: int,
    statement_id: int,
) -> CreditCardStatementOut:
    card = await cc_repo.get_credit_card(conn, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Credit card not found")
    stmt = await cc_repo.get_statement(conn, statement_id)
    if stmt is None or stmt.credit_card_id != card_id:
        raise HTTPException(status_code=404, detail="Statement not found")
    return _stmt_out(stmt)


@router.post("/{card_id}/statements", response_model=CreditCardStatementOut, status_code=201)
async def upload_statement(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    api_settings: Annotated[ApiSettings, Depends(get_settings)],
    card_id: int,
    file: UploadFile = File(...),
    pdf_password: str | None = Form(default=None),
) -> CreditCardStatementOut:
    card = await cc_repo.get_credit_card(conn, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Credit card not found")
    if not file.filename:
        raise HTTPException(status_code=400, detail="file name is required")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="file is empty")
    try:
        summary, line_items, preview = await build_credit_card_statement_payload(
            file.filename,
            content,
            pdf_password=pdf_password,
            issuer=card.issuer,
            settings=api_settings,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    ps = summary.get("period_start")
    pe = summary.get("period_end")
    if isinstance(ps, str):
        pass
    else:
        ps = None
    if isinstance(pe, str):
        pass
    else:
        pe = None

    sid = await cc_repo.insert_statement(
        conn,
        credit_card_id=card_id,
        filename=file.filename,
        period_start=ps,
        period_end=pe,
        extraction_preview=preview,
        summary_json=dumps_summary(summary),
        line_items_json=dumps_line_items(line_items),
        status="pending_review",
    )
    st = await cc_repo.get_statement(conn, sid)
    if st is None:
        raise HTTPException(status_code=500, detail="statement not found after insert")
    return _stmt_out(st)


@router.post(
    "/{card_id}/statements/{statement_id}/apply",
    response_model=CreditCardStatementApplyResponse,
)
async def apply_statement(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    card_id: int,
    statement_id: int,
) -> CreditCardStatementApplyResponse:
    card = await cc_repo.get_credit_card(conn, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Credit card not found")
    stmt = await cc_repo.get_statement(conn, statement_id)
    if stmt is None or stmt.credit_card_id != card_id:
        raise HTTPException(status_code=404, detail="Statement not found")
    if stmt.status == "applied":
        raise HTTPException(status_code=409, detail="Statement already applied to transactions")

    items = line_items_json_loads(stmt.line_items_json)
    if not items:
        raise HTTPException(
            status_code=400,
            detail=(
                "No parsed line items — upload a PDF/CSV with transaction lines, "
                "or add a CSV with date, amount, category."
            ),
        )

    default_pm = infer_cc_payment_mode(card.issuer)
    imported = 0
    for it in items:
        try:
            d_raw = it.get("date")
            if not d_raw:
                continue
            tx_date = parse_transaction_date(str(d_raw))
            ap = int(it.get("amount_paise") or 0)
            if ap <= 0:
                continue
            cat = Category.from_string(str(it.get("category") or "Other")).value
            pm_raw = str(it.get("payment_mode") or default_pm)
            pm = PaymentMode.from_string(pm_raw).value
            desc = it.get("description")
            merchant = str(desc)[:2000] if desc else None
            tx_type_raw = it.get("transaction_type") or "debit"
            tx_type = str(tx_type_raw) if tx_type_raw in ("debit", "credit") else "debit"
            await tx_repo.insert_transaction(
                conn,
                tx_date=tx_date,
                amount_paise=Paise(ap),
                category=cat,
                merchant=merchant,
                payment_mode=pm,
                account=card.name,
                notes=f"CC import · stmt #{statement_id}",
                source="cc_statement_import",
                transaction_type=tx_type,
                account_id=card.account_id,
            )
            imported += 1
        except (ValueError, TypeError):
            continue

    await cc_repo.update_statement_status(conn, statement_id, status="applied")

    summary = summary_json_loads(stmt.summary_json)
    new_bal: int | None = None
    if "closing_balance_paise" in summary:
        new_bal = int(summary["closing_balance_paise"])
    elif "total_due_paise" in summary:
        new_bal = int(summary["total_due_paise"])

    if new_bal is not None:
        merged = replace(card, current_balance_paise=new_bal)
        await cc_repo.update_credit_card_row(conn, merged)

    return CreditCardStatementApplyResponse(imported_count=imported, updated_balance_paise=new_bal)


@router.get("/{card_id}/emis", response_model=list[CreditCardEmiOut])
async def list_emis(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    card_id: int,
) -> list[CreditCardEmiOut]:
    card = await cc_repo.get_credit_card(conn, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Credit card not found")
    rows = await cc_repo.list_emis_for_card(conn, card_id)
    return [_emi_out(r) for r in rows]


@router.post("/{card_id}/emis", response_model=CreditCardEmiOut, status_code=201)
async def create_emi(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    card_id: int,
    body: CreditCardEmiCreateBody,
) -> CreditCardEmiOut:
    card = await cc_repo.get_credit_card(conn, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Credit card not found")
    if body.installments_paid > body.tenure_months:
        raise HTTPException(
            status_code=400,
            detail="installments_paid cannot exceed tenure_months",
        )
    eid = await cc_repo.insert_emi(
        conn,
        credit_card_id=card_id,
        description=body.description.strip(),
        limit_blocked_paise=body.limit_blocked_paise,
        emi_amount_paise=body.emi_amount_paise,
        tenure_months=body.tenure_months,
        installments_paid=body.installments_paid,
        is_active=body.is_active,
        notes=body.notes.strip() if body.notes else None,
        loan_type=_emi_opt_str(body.loan_type),
        creation_date=_emi_opt_str(body.creation_date),
        finish_date=_emi_opt_str(body.finish_date),
        principal_paise=body.principal_paise,
        outstanding_instalment_paise=body.outstanding_instalment_paise,
    )
    row = await cc_repo.get_emi(conn, eid)
    if row is None:
        raise HTTPException(status_code=500, detail="EMI not found after insert")
    return _emi_out(row)


@router.put("/{card_id}/emis/{emi_id}", response_model=CreditCardEmiOut)
async def put_emi(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    card_id: int,
    emi_id: int,
    body: CreditCardEmiPutBody,
) -> CreditCardEmiOut:
    card = await cc_repo.get_credit_card(conn, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Credit card not found")
    existing = await cc_repo.get_emi(conn, emi_id)
    if existing is None or existing.credit_card_id != card_id:
        raise HTTPException(status_code=404, detail="EMI not found")
    merged = _merge_emi(existing, body)
    if merged.installments_paid > merged.tenure_months:
        raise HTTPException(
            status_code=400,
            detail="installments_paid cannot exceed tenure_months",
        )
    await cc_repo.update_emi_row(conn, merged)
    return _emi_out(merged)


@router.delete("/{card_id}/emis/{emi_id}", status_code=204)
async def delete_emi(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    card_id: int,
    emi_id: int,
) -> None:
    card = await cc_repo.get_credit_card(conn, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Credit card not found")
    existing = await cc_repo.get_emi(conn, emi_id)
    if existing is None or existing.credit_card_id != card_id:
        raise HTTPException(status_code=404, detail="EMI not found")
    await cc_repo.delete_emi(conn, emi_id)


@router.post("/{card_id}/emis/{emi_id}/convert-to-debt", response_model=DebtOut, status_code=201)
async def convert_emi_to_debt(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    card_id: int,
    emi_id: int,
) -> DebtOut:
    """Convert a CC EMI plan into a tracked Debt entry."""
    card = await cc_repo.get_credit_card(conn, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Credit card not found")
    emi = await cc_repo.get_emi(conn, emi_id)
    if emi is None or emi.credit_card_id != card_id:
        raise HTTPException(status_code=404, detail="EMI not found")

    principal = emi.principal_paise if emi.principal_paise is not None else emi.limit_blocked_paise
    remaining = max(0, emi.tenure_months - emi.installments_paid)
    outstanding = remaining * emi.emi_amount_paise

    debt_id = await debt_repo.insert_debt(
        conn,
        name=emi.description,
        lender=card.name,
        type_="credit_card_emi",
        original_amount_paise=principal,
        current_balance_paise=outstanding,
        emi_paise=emi.emi_amount_paise,
        rate_percent=None,
        start_date=emi.creation_date,
        next_emi_date=None,
        status="active",
        tenure_months=emi.tenure_months,
        first_emi_date=emi.creation_date,
    )
    row = await debt_repo.get_debt(conn, debt_id)
    if row is None:
        raise HTTPException(status_code=500, detail="Failed to retrieve created debt")
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


@router.delete("/{card_id}/statements/{statement_id}", status_code=204)
async def delete_statement(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    card_id: int,
    statement_id: int,
) -> None:
    card = await cc_repo.get_credit_card(conn, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Credit card not found")
    stmt = await cc_repo.get_statement(conn, statement_id)
    if stmt is None or stmt.credit_card_id != card_id:
        raise HTTPException(status_code=404, detail="Statement not found")
    await cc_repo.delete_statement(conn, statement_id)
