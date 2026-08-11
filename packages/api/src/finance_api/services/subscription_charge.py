"""Manual subscription charge posting via LedgerService."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import aiosqlite

from finance_api.services.amortization import advance_months
from finance_common.ledger import builders
from finance_common.ledger import service as ledger_service
from finance_common.ledger.errors import LedgerError
from finance_common.ledger.models import PostTransactionInput
from finance_common.repositories import accounts as accounts_repo
from finance_common.repositories import subscriptions as sub_repo
from finance_common.repositories.subscriptions import SubscriptionRow

_UNCATEGORIZED_EXPENSE = "Uncategorized Expense"


async def uncategorized_expense_id(conn: aiosqlite.Connection) -> int:
    account = await accounts_repo.get_account_by_name(conn, _UNCATEGORIZED_EXPENSE)
    if account is None:
        raise LedgerError(
            f"Required system account {_UNCATEGORIZED_EXPENSE!r} does not exist"
        )
    return account.id


def _is_credit_card_account(account: accounts_repo.AccountRow) -> bool:
    return account.account_class == "liability_cc" or account.type == "credit_card"


def advance_billing_date(
    *,
    current_next: str | None,
    payment_date: date,
    billing_cycle: str,
) -> str:
    """Advance next billing date by one cycle from the appropriate base date."""
    if not current_next or not current_next.strip():
        base = payment_date
    else:
        next_d = date.fromisoformat(current_next[:10])
        base = payment_date if next_d <= payment_date else next_d

    cycle = billing_cycle.lower().strip()
    if cycle == "weekly":
        return (base + timedelta(days=7)).isoformat()
    if cycle == "monthly":
        return advance_months(base, 1).isoformat()
    if cycle == "quarterly":
        return advance_months(base, 3).isoformat()
    if cycle == "yearly":
        return advance_months(base, 12).isoformat()
    return advance_months(base, 1).isoformat()


async def post_subscription_charge(
    conn: aiosqlite.Connection,
    *,
    sub: SubscriptionRow,
    payment_date: str,
    amount_paise: int | None = None,
    account_id: int | None = None,
) -> tuple[int, SubscriptionRow]:
    """Post expense via LedgerService; advance next_billing_date."""
    tx_date = date.fromisoformat(payment_date[:10])

    charge_amount = amount_paise if amount_paise is not None else sub.amount_paise
    if charge_amount <= 0:
        raise LedgerError("amount_paise must be positive")

    payment_account_id = account_id if account_id is not None else sub.account_id
    if payment_account_id is None:
        raise LedgerError("account_id required (on subscription or in request body)")

    payment_account = await accounts_repo.get_account(conn, payment_account_id)
    if payment_account is None:
        raise LedgerError("account_id not found")

    category = sub.category.strip() if sub.category and sub.category.strip() else "Subscriptions"
    expense_account_id = await uncategorized_expense_id(conn)

    if _is_credit_card_account(payment_account):
        postings = builders.build_cc_swipe(
            cc_id=payment_account_id,
            expense_account_id=expense_account_id,
            amount_paise=charge_amount,
            category=category,
        )
    else:
        postings = builders.build_bank_expense(
            bank_id=payment_account_id,
            expense_account_id=expense_account_id,
            amount_paise=charge_amount,
            category=category,
        )

    ledger_transaction_id = await ledger_service.post(
        conn,
        PostTransactionInput(
            tx_date=tx_date,
            postings=postings,
            payee=sub.name,
            notes=f"Subscription charge · {sub.name}",
            source="subscription",
            external_key=(
                f"subscription_charge:{sub.id}:{payment_date[:10]}:{charge_amount}"
            ),
        ),
    )

    new_next = advance_billing_date(
        current_next=sub.next_billing_date,
        payment_date=tx_date,
        billing_cycle=sub.billing_cycle,
    )
    updated = replace(sub, next_billing_date=new_next)
    await sub_repo.update_subscription_row(conn, updated)
    return ledger_transaction_id, updated
