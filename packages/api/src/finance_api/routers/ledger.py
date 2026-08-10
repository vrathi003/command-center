"""HTTP API for immutable double-entry ledger transactions."""

from __future__ import annotations

import calendar
from datetime import date
from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query

from finance_api.deps import get_conn
from finance_api.deps_ledger import require_ledger_writes
from finance_api.schemas.ledger import (
    LedgerAccountBalanceResponse,
    LedgerMonthSummaryResponse,
    LedgerPostingResponse,
    LedgerTransactionCreate,
    LedgerTransactionCreated,
    LedgerTransactionResponse,
)
from finance_common.ledger import balances, builders, reports
from finance_common.ledger import service as ledger_service
from finance_common.ledger.errors import LedgerError
from finance_common.ledger.models import NewPosting, PostedTransaction, PostTransactionInput

router = APIRouter(prefix="/ledger", tags=["ledger"])


def _require_int(value: int | None, field: str) -> int:
    if value is None:
        raise HTTPException(status_code=422, detail=f"{field} is required for this pattern")
    return value


def _require_str(value: str | None, field: str) -> str:
    if value is None:
        raise HTTPException(status_code=422, detail=f"{field} is required for this pattern")
    return value


def _pattern_postings(body: LedgerTransactionCreate) -> tuple[NewPosting, ...]:
    if body.pattern == "custom":
        if body.postings is None:
            raise HTTPException(status_code=422, detail="postings are required for custom")
        return tuple(
            NewPosting(posting.account_id, posting.amount_paise, posting.category)
            for posting in body.postings
        )

    amount = _require_int(body.amount_paise, "amount_paise")
    if amount <= 0:
        raise HTTPException(status_code=422, detail="amount_paise must be positive")

    if body.pattern == "bank_expense":
        return builders.build_bank_expense(
            bank_id=_require_int(body.bank_account_id, "bank_account_id"),
            expense_account_id=_require_int(body.expense_account_id, "expense_account_id"),
            amount_paise=amount,
            category=_require_str(body.category, "category"),
        )
    if body.pattern == "bank_income":
        return builders.build_bank_income(
            bank_id=_require_int(body.bank_account_id, "bank_account_id"),
            income_account_id=_require_int(body.income_account_id, "income_account_id"),
            amount_paise=amount,
            category=_require_str(body.category, "category"),
        )
    if body.pattern == "transfer":
        return builders.build_transfer(
            from_account_id=_require_int(body.from_account_id, "from_account_id"),
            to_account_id=_require_int(body.to_account_id, "to_account_id"),
            amount_paise=amount,
        )
    if body.pattern == "cc_swipe":
        return builders.build_cc_swipe(
            cc_id=_require_int(body.cc_account_id, "cc_account_id"),
            expense_account_id=_require_int(body.expense_account_id, "expense_account_id"),
            amount_paise=amount,
            category=_require_str(body.category, "category"),
        )
    if body.pattern == "cc_bill_pay":
        return builders.build_cc_bill_pay(
            bank_id=_require_int(body.bank_account_id, "bank_account_id"),
            cc_id=_require_int(body.cc_account_id, "cc_account_id"),
            amount_paise=amount,
        )
    return builders.build_investment_buy(
        bank_id=_require_int(body.bank_account_id, "bank_account_id"),
        investment_account_id=_require_int(body.investment_account_id, "investment_account_id"),
        amount_paise=amount,
    )


def _transaction_response(transaction: PostedTransaction) -> LedgerTransactionResponse:
    return LedgerTransactionResponse(
        id=transaction.id,
        date=transaction.date,
        payee=transaction.payee,
        notes=transaction.notes,
        tags=transaction.tags,
        source=transaction.source,
        status=transaction.status,
        external_key=transaction.external_key,
        postings=[
            LedgerPostingResponse(
                id=posting.id,
                account_id=posting.account_id,
                amount_paise=posting.amount_paise,
                category=posting.category,
            )
            for posting in transaction.postings
        ],
    )


@router.post("/transactions", response_model=LedgerTransactionCreated, status_code=201)
async def create_transaction(
    body: LedgerTransactionCreate,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    _: Annotated[None, Depends(require_ledger_writes)],
) -> LedgerTransactionCreated:
    try:
        transaction_id = await ledger_service.post(
            conn,
            PostTransactionInput(
                tx_date=body.date,
                postings=_pattern_postings(body),
                payee=body.payee,
                notes=body.notes,
                tags=body.tags,
                source=body.source,
                external_key=body.external_key,
            ),
        )
    except LedgerError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return LedgerTransactionCreated(id=transaction_id)


@router.post("/transactions/{transaction_id}/void", response_model=LedgerTransactionResponse)
async def void_transaction(
    transaction_id: int,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    _: Annotated[None, Depends(require_ledger_writes)],
) -> LedgerTransactionResponse:
    try:
        await ledger_service.void(conn, transaction_id)
        return _transaction_response(await ledger_service.get_transaction(conn, transaction_id))
    except LedgerError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/transactions/{transaction_id}", response_model=LedgerTransactionResponse)
async def get_transaction(
    transaction_id: int,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> LedgerTransactionResponse:
    try:
        return _transaction_response(await ledger_service.get_transaction(conn, transaction_id))
    except LedgerError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/accounts/{account_id}/balance", response_model=LedgerAccountBalanceResponse)
async def get_account_balance(
    account_id: int,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> LedgerAccountBalanceResponse:
    return LedgerAccountBalanceResponse(
        account_id=account_id,
        balance_paise=await balances.account_balance_paise(conn, account_id),
    )


@router.get("/summary/month", response_model=LedgerMonthSummaryResponse)
async def get_month_summary(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    year: int = Query(ge=1, le=9999),
    month: int = Query(ge=1, le=12),
) -> LedgerMonthSummaryResponse:
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    cash_accounts = await conn.execute("SELECT id FROM accounts WHERE account_class = 'asset_cash'")
    cash_account_ids = [int(row[0]) for row in await cash_accounts.fetchall()]
    cash_in, cash_out = await reports.cash_flow_for_accounts(
        conn, account_ids=cash_account_ids, start=start, end=end
    )
    _, _, net_worth = await balances.net_worth_totals(conn, as_of=end)
    return LedgerMonthSummaryResponse(
        budget_spend_month_paise=await reports.budget_spend_total(conn, start=start, end=end),
        cash_out_month_paise=cash_out,
        cash_in_month_paise=cash_in,
        net_worth_paise=net_worth,
        budget_spend_by_category=await reports.budget_spend_by_category(conn, start=start, end=end),
    )
