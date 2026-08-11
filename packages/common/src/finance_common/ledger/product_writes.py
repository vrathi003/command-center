"""Product-facing ledger posts (dashboard-compatible; no HTTP types).

Used by the Discord bot under ``ledger_engine=double_entry``. The API may
adopt these helpers later; today it duplicates the same plan+post flow.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import aiosqlite

from finance_common.intake.models import Candidate
from finance_common.intake.posting_plan import IntakePlanError, plan_postings, plan_transfer
from finance_common.ledger import service as ledger_service
from finance_common.ledger.errors import LedgerError
from finance_common.ledger.models import PostedTransaction, PostTransactionInput
from finance_common.migration import facade as ledger_facade
from finance_common.repositories import accounts as accounts_repo

ACCOUNT_REQUIRED_MSG = (
    "Include an account in the log line (or set it on the template). "
    "Required when ledger_engine is double_entry."
)


class ProductWriteError(Exception):
    """User-facing failure while planning or posting a product ledger write."""


async def plan_manual(
    conn: aiosqlite.Connection,
    *,
    tx_date: date,
    amount_paise: int,
    category: str,
    merchant: str | None,
    transaction_type: str,
    account_id: int | None,
    notes: str | None,
    tags: str | None = None,
    source: str = "discord",
    external_key: str | None = None,
) -> PostTransactionInput:
    """Build a debit/credit ledger input; raises ProductWriteError on validation failure."""
    if account_id is None:
        raise ProductWriteError(ACCOUNT_REQUIRED_MSG)
    account = await accounts_repo.get_account(conn, account_id)
    if account is None:
        raise ProductWriteError("account_id not found")
    try:
        plan = await plan_postings(
            conn,
            Candidate(
                source=source,
                tx_date=tx_date,
                amount_paise=amount_paise,
                direction="out" if transaction_type == "debit" else "in",
                suggested_account_id=account_id,
                payee=merchant,
                narration=notes,
                suggested_category=category,
                external_key=external_key,
            ),
        )
        return replace(plan, tags=tags)
    except IntakePlanError as exc:
        raise ProductWriteError(str(exc)) from exc


async def post_manual(
    conn: aiosqlite.Connection,
    *,
    tx_date: date,
    amount_paise: int,
    category: str,
    merchant: str | None,
    transaction_type: str,
    account_id: int | None,
    notes: str | None,
    tags: str | None = None,
    source: str = "discord",
    external_key: str | None = None,
) -> int:
    plan = await plan_manual(
        conn,
        tx_date=tx_date,
        amount_paise=amount_paise,
        category=category,
        merchant=merchant,
        transaction_type=transaction_type,
        account_id=account_id,
        notes=notes,
        tags=tags,
        source=source,
        external_key=external_key,
    )
    try:
        return await ledger_service.post(conn, plan)
    except LedgerError as exc:
        raise ProductWriteError(str(exc)) from exc


async def post_transfer(
    conn: aiosqlite.Connection,
    *,
    tx_date: date,
    amount_paise: int,
    from_account_id: int,
    to_account_id: int,
    notes: str | None,
    tags: str | None = None,
    source: str = "discord",
    external_key: str | None = None,
) -> int:
    try:
        plan = await plan_transfer(
            conn,
            from_account_id=from_account_id,
            to_account_id=to_account_id,
            amount_paise=amount_paise,
            tx_date=tx_date,
            source=source,
            notes=notes,
            external_key=external_key,
        )
        plan = replace(plan, tags=tags)
        return await ledger_service.post(conn, plan)
    except IntakePlanError as exc:
        raise ProductWriteError(str(exc)) from exc
    except LedgerError as exc:
        raise ProductWriteError(str(exc)) from exc


async def void_posted(conn: aiosqlite.Connection, transaction_id: int) -> None:
    try:
        await ledger_service.void(conn, transaction_id)
    except LedgerError as exc:
        raise ProductWriteError(str(exc)) from exc


async def get_posted_discord(
    conn: aiosqlite.Connection, transaction_id: int
) -> PostedTransaction:
    try:
        tx = await ledger_service.get_transaction(conn, transaction_id)
    except LedgerError as exc:
        raise ProductWriteError("Transaction not found.") from exc
    if tx.status != "posted":
        raise ProductWriteError("Transaction not found.")
    if tx.source != "discord":
        raise ProductWriteError("Only Discord-logged rows can be edited here.")
    return tx


async def cash_account_id_for_posted(
    conn: aiosqlite.Connection, transaction: PostedTransaction
) -> int:
    row = await ledger_facade.transaction_row(conn, transaction)
    account_id = row.get("account_id")
    if not isinstance(account_id, int):
        raise ProductWriteError("Could not resolve account for this transaction.")
    return account_id


async def latest_posted_id_by_source(
    conn: aiosqlite.Connection, *, source: str
) -> int | None:
    cursor = await conn.execute(
        """
        SELECT id FROM ledger_transactions
        WHERE source = ? AND status = 'posted'
        ORDER BY datetime(created_at) DESC, id DESC
        LIMIT 1
        """,
        (source,),
    )
    row = await cursor.fetchone()
    return None if row is None else int(row[0])
