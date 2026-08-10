"""Compatibility facade that presents posted ledger entries as legacy transactions."""

from __future__ import annotations

from datetime import date

import aiosqlite

from finance_common.ledger import service as ledger_service
from finance_common.ledger.models import PostedTransaction

_CASH_OR_CC_CLASSES = frozenset({"asset_cash", "liability_cc"})


async def _account_details(
    conn: aiosqlite.Connection, transaction: PostedTransaction
) -> dict[int, tuple[str, str]]:
    account_ids = tuple(posting.account_id for posting in transaction.postings)
    placeholders = ", ".join("?" for _ in account_ids)
    cursor = await conn.execute(
        f"SELECT id, name, account_class FROM accounts WHERE id IN ({placeholders})",  # noqa: S608
        account_ids,
    )
    return {
        int(row[0]): (str(row[1]), str(row[2]))
        for row in await cursor.fetchall()
    }


def _is_asset_or_liability(account_class: str) -> bool:
    return account_class.startswith(("asset_", "liability_"))


async def transaction_row(
    conn: aiosqlite.Connection, transaction: PostedTransaction
) -> dict[str, object]:
    """Map one posted ledger transaction to the legacy TransactionRow shape."""
    details = await _account_details(conn, transaction)
    postings = [
        (posting, *details[posting.account_id]) for posting in transaction.postings
    ]
    cash_or_cc = [
        posting for posting in postings if posting[2] in _CASH_OR_CC_CLASSES
    ]
    is_transfer = len(postings) == 2 and all(
        _is_asset_or_liability(account_class) for _, _, account_class in postings
    )
    if is_transfer:
        negative_cash_or_cc = [
            posting for posting in cash_or_cc if posting[0].amount_paise < 0
        ]
        cash_leg = next(
            (
                posting
                for posting in negative_cash_or_cc
                if posting[2] == "asset_cash"
            ),
            negative_cash_or_cc[0],
        )
        transaction_type = "transfer"
        transfer_pair_id: str | None = transaction.external_key or f"ledger:{transaction.id}"
    else:
        cash_leg = cash_or_cc[0]
        transaction_type = "debit" if cash_leg[0].amount_paise < 0 else "credit"
        transfer_pair_id = None

    category = next(
        (
            posting.category
            for posting, _, account_class in postings
            if account_class in {"expense", "income"} and posting.category
        ),
        "Other",
    )
    posting, account_name, _ = cash_leg
    return {
        "id": transaction.id,
        "date": transaction.date.isoformat(),
        "amount_paise": sum(abs(p.amount_paise) for p in transaction.postings) // 2,
        "category": category,
        "merchant": transaction.payee,
        "payment_mode": "Other",
        "account": account_name,
        "notes": transaction.notes,
        "transaction_type": transaction_type,
        "source": transaction.source,
        "account_id": posting.account_id,
        "transfer_pair_id": transfer_pair_id,
        "tags": transaction.tags,
    }


async def list_transaction_rows(
    conn: aiosqlite.Connection,
    *,
    limit: int,
    start_date: str | None,
    end_date: str | None,
    account: str | None,
    account_id: int | None,
) -> list[dict[str, object]]:
    """List posted ledger transactions in the legacy TransactionRow shape."""
    rows = [
        await transaction_row(conn, transaction)
        for transaction in await ledger_service.list_transactions(
            conn,
            start=None if start_date is None else date.fromisoformat(start_date),
            end=None if end_date is None else date.fromisoformat(end_date),
            limit=limit,
        )
    ]
    if account is not None:
        rows = [row for row in rows if row["account"] == account]
    if account_id is not None:
        rows = [row for row in rows if row["account_id"] == account_id]
    return rows


async def get_transaction_row(
    conn: aiosqlite.Connection, transaction_id: int
) -> dict[str, object]:
    """Get a posted ledger transaction in the legacy TransactionRow shape."""
    return await transaction_row(conn, await ledger_service.get_transaction(conn, transaction_id))
