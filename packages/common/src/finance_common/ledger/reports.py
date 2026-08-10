"""Read-only budget-spend and cash-flow queries over posted ledger postings."""

from __future__ import annotations

from datetime import date

import aiosqlite


async def budget_spend_by_category(
    conn: aiosqlite.Connection, *, start: date, end: date
) -> dict[str, int]:
    """Return expense debits by category for posted transactions in a date range."""
    cursor = await conn.execute(
        """
        SELECT COALESCE(posting.category, 'Uncategorized'), SUM(posting.amount_paise)
        FROM ledger_postings AS posting
        JOIN ledger_transactions AS tx ON tx.id = posting.transaction_id
        JOIN accounts AS account ON account.id = posting.account_id
        WHERE account.account_class = 'expense'
          AND posting.amount_paise > 0
          AND tx.status = 'posted'
          AND tx.date BETWEEN ? AND ?
        GROUP BY COALESCE(posting.category, 'Uncategorized')
        """,
        (start.isoformat(), end.isoformat()),
    )
    return {str(category): int(amount_paise) for category, amount_paise in await cursor.fetchall()}


async def budget_spend_total(conn: aiosqlite.Connection, *, start: date, end: date) -> int:
    """Return total expense debits for posted transactions in a date range."""
    cursor = await conn.execute(
        """
        SELECT COALESCE(SUM(posting.amount_paise), 0)
        FROM ledger_postings AS posting
        JOIN ledger_transactions AS tx ON tx.id = posting.transaction_id
        JOIN accounts AS account ON account.id = posting.account_id
        WHERE account.account_class = 'expense'
          AND posting.amount_paise > 0
          AND tx.status = 'posted'
          AND tx.date BETWEEN ? AND ?
        """,
        (start.isoformat(), end.isoformat()),
    )
    row = await cursor.fetchone()
    return 0 if row is None else int(row[0])


async def cash_flow_for_accounts(
    conn: aiosqlite.Connection,
    *,
    account_ids: list[int],
    start: date,
    end: date,
) -> tuple[int, int]:
    """Return cash-in and cash-out for the requested accounts in a date range."""
    if not account_ids:
        return 0, 0

    placeholders = ", ".join("?" for _ in account_ids)
    cursor = await conn.execute(
        f"""
        SELECT
            COALESCE(SUM(
                CASE WHEN posting.amount_paise > 0 THEN posting.amount_paise ELSE 0 END
            ), 0),
            COALESCE(SUM(
                CASE WHEN posting.amount_paise < 0 THEN -posting.amount_paise ELSE 0 END
            ), 0)
        FROM ledger_postings AS posting
        JOIN ledger_transactions AS tx ON tx.id = posting.transaction_id
        WHERE posting.account_id IN ({placeholders})
          AND tx.status = 'posted'
          AND tx.date BETWEEN ? AND ?
        """,  # noqa: S608
        (*account_ids, start.isoformat(), end.isoformat()),
    )
    row = await cursor.fetchone()
    return (0, 0) if row is None else (int(row[0]), int(row[1]))
