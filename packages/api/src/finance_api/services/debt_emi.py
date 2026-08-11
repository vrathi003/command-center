"""EMI auto-advance — legacy balance scrub or ledger-backed auto-post."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import aiosqlite
from loguru import logger

from finance_api.services.amortization import (
    advance_months,
    build_schedule,
    compute_emi_advance,
    emis_due_count,
)
from finance_common.ledger import builders
from finance_common.ledger import service as ledger_service
from finance_common.ledger.balances import account_balance_paise
from finance_common.ledger.errors import LedgerError
from finance_common.ledger.models import PostTransactionInput
from finance_common.project_config import load_project_config
from finance_common.repositories import accounts as accounts_repo
from finance_common.repositories import debts as debt_repo
from finance_common.repositories.debts import DebtRow

_UNCATEGORIZED_EXPENSE = "Uncategorized Expense"


async def loan_outstanding_paise(conn: aiosqlite.Connection, account_id: int) -> int:
    balance = await account_balance_paise(conn, account_id)
    return max(0, -balance)


async def uncategorized_expense_id(conn: aiosqlite.Connection) -> int:
    account = await accounts_repo.get_account_by_name(conn, _UNCATEGORIZED_EXPENSE)
    if account is None:
        raise LedgerError(
            f"Required system account {_UNCATEGORIZED_EXPENSE!r} does not exist"
        )
    return account.id


def _schedule_rows(debt: DebtRow) -> list:
    principal = debt.original_amount_paise or debt.current_balance_paise
    rows, _ = build_schedule(
        principal,
        debt.rate_percent,
        debt.emi_paise,
        tenure_months=debt.tenure_months,
    )
    return rows


def default_emi_split(debt: DebtRow, tx_date: date) -> tuple[int, int]:
    schedule_ref = debt.first_emi_date or debt.start_date
    if not schedule_ref:
        emi = debt.emi_paise or 0
        return emi, 0

    ref = date.fromisoformat(schedule_ref[:10])
    if debt.next_emi_date:
        payment_num = emis_due_count(ref, date.fromisoformat(debt.next_emi_date[:10]))
    else:
        payment_num = emis_due_count(ref, tx_date)

    sched = _schedule_rows(debt)
    if not sched or payment_num < 1 or payment_num > len(sched):
        emi = debt.emi_paise or 0
        return emi, 0

    row = sched[payment_num - 1]
    return row.principal_paise, row.interest_paise


def advance_after_one_emi(debt: DebtRow) -> tuple[str | None, str]:
    if debt.next_emi_date:
        due = date.fromisoformat(debt.next_emi_date[:10])
        new_next = advance_months(due, 1).isoformat()
    elif debt.first_emi_date or debt.start_date:
        ref = date.fromisoformat((debt.first_emi_date or debt.start_date)[:10])
        new_next = advance_months(ref, 1).isoformat()
    else:
        new_next = debt.next_emi_date

    new_status = "closed" if debt.current_balance_paise == 0 else "active"
    return new_next, new_status


def _is_emi_due(debt: DebtRow, today: date) -> bool:
    if debt.status != "active":
        return False
    if not debt.emi_paise or debt.emi_paise <= 0:
        return False
    if debt.next_emi_date:
        return date.fromisoformat(debt.next_emi_date[:10]) <= today
    schedule_ref = debt.first_emi_date or debt.start_date
    if schedule_ref:
        ref = date.fromisoformat(schedule_ref[:10])
        return emis_due_count(ref, today) > 0
    return False


def _emi_tx_date(debt: DebtRow) -> date | None:
    if debt.next_emi_date:
        return date.fromisoformat(debt.next_emi_date[:10])
    schedule_ref = debt.first_emi_date or debt.start_date
    if schedule_ref:
        return date.fromisoformat(schedule_ref[:10])
    return None


async def post_emi_and_advance(
    conn: aiosqlite.Connection,
    debt: DebtRow,
    *,
    tx_date: date,
    principal_paise: int | None = None,
    interest_paise: int | None = None,
    payment_account_id: int | None = None,
    source: str = "dashboard",
) -> tuple[int, DebtRow]:
    """Post one EMI through the ledger and advance the debt schedule."""
    if debt.account_id is None:
        raise LedgerError("Debt has no linked loan account")

    bank_id = payment_account_id or debt.payment_account_id
    if bank_id is None:
        raise LedgerError("payment_account_id required")

    if await accounts_repo.get_account(conn, bank_id) is None:
        raise LedgerError("payment_account_id not found")
    if await accounts_repo.get_account(conn, debt.account_id) is None:
        raise LedgerError("loan account not found")

    if principal_paise is None or interest_paise is None:
        default_principal, default_interest = default_emi_split(debt, tx_date)
        principal_paise = default_principal if principal_paise is None else principal_paise
        interest_paise = default_interest if interest_paise is None else interest_paise

    total = principal_paise + interest_paise
    if total <= 0:
        raise LedgerError("EMI total must be positive")

    expense_account_id = await uncategorized_expense_id(conn)
    ledger_transaction_id = await ledger_service.post(
        conn,
        PostTransactionInput(
            tx_date=tx_date,
            postings=builders.build_emi_payment(
                bank_id=bank_id,
                loan_id=debt.account_id,
                expense_account_id=expense_account_id,
                principal_paise=principal_paise,
                interest_paise=interest_paise,
            ),
            payee=debt.name,
            notes=f"EMI payment · {debt.name}",
            source=source,
            external_key=f"debt_emi:{debt.id}:{tx_date.isoformat()}:{total}",
        ),
    )

    outstanding = await loan_outstanding_paise(conn, debt.account_id)
    new_next, new_status = advance_after_one_emi(
        replace(debt, current_balance_paise=outstanding)
    )
    updated = replace(
        debt,
        current_balance_paise=outstanding,
        next_emi_date=new_next,
        status=new_status,
        payment_account_id=bank_id,
    )
    await debt_repo.update_debt_row(conn, updated)
    return ledger_transaction_id, updated


async def auto_advance_active_debts(conn: aiosqlite.Connection) -> int:
    """Persist EMI state for overdue active debts. Returns count updated."""
    debts = await debt_repo.list_debts(conn, status="active")
    updated = 0
    for debt in debts:
        if await auto_advance_debt(conn, debt) is not None:
            updated += 1
    return updated


async def auto_advance_debt(conn: aiosqlite.Connection, debt: DebtRow) -> DebtRow | None:
    """Advance a single debt if its EMI is overdue. Returns updated row or None if unchanged."""
    project_config = await load_project_config(conn)
    if project_config.ledger_engine != "double_entry":
        result = compute_emi_advance(debt)
        if not result:
            return None
        new_bal, new_next_date, new_status = result
        updated = replace(
            debt,
            current_balance_paise=new_bal,
            next_emi_date=new_next_date,
            status=new_status,
        )
        await debt_repo.update_debt_row(conn, updated)
        return updated

    today = date.today()
    if not _is_emi_due(debt, today):
        return None

    if not debt.account_id or not debt.payment_account_id or not debt.emi_paise:
        return None

    tx_date = _emi_tx_date(debt)
    if tx_date is None:
        return None

    try:
        _, updated = await post_emi_and_advance(
            conn,
            debt,
            tx_date=tx_date,
            source="job",
        )
    except LedgerError as exc:
        logger.warning("EMI auto-post skipped for debt {}: {}", debt.id, exc)
        return None
    return updated
