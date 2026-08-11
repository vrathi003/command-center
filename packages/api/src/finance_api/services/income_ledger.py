"""Record income from planning streams through the ledger."""

from __future__ import annotations

from datetime import date

import aiosqlite

from finance_common.ledger import builders
from finance_common.ledger import service as ledger_service
from finance_common.ledger.errors import LedgerError
from finance_common.ledger.models import PostTransactionInput
from finance_common.repositories import accounts as accounts_repo
from finance_common.repositories.income_sources import IncomeSourceRow

_UNCATEGORIZED_INCOME = "Uncategorized Income"
_DEFAULT_CATEGORY = "Salary"


async def uncategorized_income_id(conn: aiosqlite.Connection) -> int:
    account = await accounts_repo.get_account_by_name(conn, _UNCATEGORIZED_INCOME)
    if account is None:
        raise LedgerError(
            f"Required system account {_UNCATEGORIZED_INCOME!r} does not exist"
        )
    return account.id


async def post_income_credit(
    conn: aiosqlite.Connection,
    *,
    source: IncomeSourceRow,
    payment_date: str,
    amount_paise: int | None = None,
    account_id: int | None = None,
    category: str | None = None,
) -> tuple[int, IncomeSourceRow]:
    """Post bank income via LedgerService; return ledger tx id and unchanged source."""
    tx_date = date.fromisoformat(payment_date[:10])

    credit_amount = amount_paise if amount_paise is not None else source.amount_paise
    if credit_amount is None or credit_amount <= 0:
        raise LedgerError("amount_paise must be positive")

    bank_account_id = account_id if account_id is not None else source.default_account_id
    if bank_account_id is None:
        raise LedgerError("account_id required (on income stream or in request body)")

    bank = await accounts_repo.get_account(conn, bank_account_id)
    if bank is None:
        raise LedgerError("account_id not found")

    income_category = (
        category.strip()
        if category and category.strip()
        else (
            source.category.strip()
            if source.category and source.category.strip()
            else _DEFAULT_CATEGORY
        )
    )
    income_account_id = await uncategorized_income_id(conn)

    postings = builders.build_bank_income(
        bank_id=bank_account_id,
        income_account_id=income_account_id,
        amount_paise=credit_amount,
        category=income_category,
    )
    ledger_transaction_id = await ledger_service.post(
        conn,
        PostTransactionInput(
            tx_date=tx_date,
            postings=postings,
            payee=source.name,
            notes=f"Income received · {source.name}",
            source="income",
            external_key=(
                f"income_credit:{source.id}:{payment_date[:10]}:{credit_amount}"
            ),
        ),
    )
    return ledger_transaction_id, source
