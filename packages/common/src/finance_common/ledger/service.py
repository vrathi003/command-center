"""Persistence operations for immutable double-entry ledger transactions."""

from __future__ import annotations

from datetime import date

import aiosqlite

from finance_common.ledger.errors import LedgerError, UnbalancedTransactionError
from finance_common.ledger.models import (
    NewPosting,
    PostedPosting,
    PostedTransaction,
    PostTransactionInput,
)


async def _existing_transaction_id(
    conn: aiosqlite.Connection, external_key: str
) -> int | None:
    cursor = await conn.execute(
        "SELECT id FROM ledger_transactions WHERE external_key = ?",
        (external_key,),
    )
    row = await cursor.fetchone()
    return None if row is None else int(row[0])


async def _verify_accounts_exist(
    conn: aiosqlite.Connection, postings: tuple[NewPosting, ...]
) -> None:
    account_ids = {posting.account_id for posting in postings}
    placeholders = ", ".join("?" for _ in account_ids)
    cursor = await conn.execute(
        f"SELECT id FROM accounts WHERE id IN ({placeholders})",  # noqa: S608
        tuple(account_ids),
    )
    found_ids = {int(row[0]) for row in await cursor.fetchall()}
    missing_ids = account_ids - found_ids
    if missing_ids:
        raise LedgerError(f"Unknown account ids: {sorted(missing_ids)}")


def _validate_postings(postings: tuple[NewPosting, ...]) -> None:
    if len(postings) < 2:
        raise LedgerError("A transaction requires at least two postings")
    if any(
        isinstance(posting.amount_paise, bool)
        or not isinstance(posting.amount_paise, int)
        for posting in postings
    ):
        raise LedgerError("Posting amounts must be integer paise")
    if sum(posting.amount_paise for posting in postings) != 0:
        raise UnbalancedTransactionError("Signed postings must sum to zero")
    if any(posting.amount_paise == 0 for posting in postings):
        raise LedgerError("Postings must not have a zero amount")


async def post(conn: aiosqlite.Connection, inp: PostTransactionInput) -> int:
    """Atomically store a balanced transaction and return its identifier."""
    if inp.external_key is not None:
        existing_id = await _existing_transaction_id(conn, inp.external_key)
        if existing_id is not None:
            return existing_id

    _validate_postings(inp.postings)
    await conn.execute("BEGIN IMMEDIATE")
    try:
        await _verify_accounts_exist(conn, inp.postings)
        cursor = await conn.execute(
            """
            INSERT INTO ledger_transactions (
                date, payee, notes, tags, source, external_key
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                inp.tx_date.isoformat(),
                inp.payee,
                inp.notes,
                inp.tags,
                inp.source,
                inp.external_key,
            ),
        )
        transaction_id = cursor.lastrowid
        if transaction_id is None:
            raise LedgerError("Unable to create ledger transaction")
        await conn.executemany(
            """
            INSERT INTO ledger_postings (transaction_id, account_id, amount_paise, category)
            VALUES (?, ?, ?, ?)
            """,
            [
                (transaction_id, posting.account_id, posting.amount_paise, posting.category)
                for posting in inp.postings
            ],
        )
        await conn.commit()
    except BaseException:
        await conn.rollback()
        raise
    return int(transaction_id)


async def void(conn: aiosqlite.Connection, transaction_id: int) -> None:
    """Void a posted transaction while retaining its postings for audit."""
    cursor = await conn.execute(
        """
        UPDATE ledger_transactions
        SET status = 'void', updated_at = datetime('now')
        WHERE id = ? AND status = 'posted'
        """,
        (transaction_id,),
    )
    if cursor.rowcount != 1:
        await conn.rollback()
        raise LedgerError(f"Transaction {transaction_id} is missing or already void")
    await conn.commit()


async def get_transaction(
    conn: aiosqlite.Connection, transaction_id: int
) -> PostedTransaction:
    """Return a persisted transaction and its postings."""
    cursor = await conn.execute(
        """
        SELECT id, date, payee, notes, tags, source, status, external_key
        FROM ledger_transactions
        WHERE id = ?
        """,
        (transaction_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        raise LedgerError(f"Transaction {transaction_id} does not exist")

    postings_cursor = await conn.execute(
        """
        SELECT id, account_id, amount_paise, category
        FROM ledger_postings
        WHERE transaction_id = ?
        ORDER BY id
        """,
        (transaction_id,),
    )
    postings = tuple(
        PostedPosting(
            id=int(posting_row[0]),
            account_id=int(posting_row[1]),
            amount_paise=int(posting_row[2]),
            category=None if posting_row[3] is None else str(posting_row[3]),
        )
        for posting_row in await postings_cursor.fetchall()
    )
    return PostedTransaction(
        id=int(row[0]),
        date=date.fromisoformat(str(row[1])),
        payee=None if row[2] is None else str(row[2]),
        notes=None if row[3] is None else str(row[3]),
        tags=None if row[4] is None else str(row[4]),
        source=str(row[5]),
        status=str(row[6]),
        external_key=None if row[7] is None else str(row[7]),
        postings=postings,
    )
