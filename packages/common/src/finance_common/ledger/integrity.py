"""Integrity checks for persisted double-entry ledger transactions."""

from __future__ import annotations

import aiosqlite

from finance_common.ledger.errors import LedgerIntegrityError


async def find_unbalanced_posted_transaction_ids(
    conn: aiosqlite.Connection,
) -> list[int]:
    """Return posted transaction identifiers whose signed postings do not net to zero."""
    cursor = await conn.execute(
        """
        SELECT tx.id
        FROM ledger_transactions AS tx
        LEFT JOIN ledger_postings AS posting ON posting.transaction_id = tx.id
        WHERE tx.status = 'posted'
        GROUP BY tx.id
        HAVING COALESCE(SUM(posting.amount_paise), 0) != 0
        ORDER BY tx.id
        """
    )
    return [int(row[0]) for row in await cursor.fetchall()]


async def assert_ledger_healthy(conn: aiosqlite.Connection) -> None:
    """Raise when any posted ledger transaction is unbalanced."""
    transaction_ids = await find_unbalanced_posted_transaction_ids(conn)
    if transaction_ids:
        raise LedgerIntegrityError(
            f"Unbalanced posted ledger transactions: {transaction_ids}"
        )
