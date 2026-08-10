"""Read-only balance and net-worth queries over posted ledger postings."""

from __future__ import annotations

from datetime import date

import aiosqlite


async def account_balance_paise(conn: aiosqlite.Connection, account_id: int) -> int:
    """Return an account's signed balance from posted ledger transactions."""
    cursor = await conn.execute(
        """
        SELECT COALESCE(SUM(posting.amount_paise), 0)
        FROM ledger_postings AS posting
        JOIN ledger_transactions AS tx ON tx.id = posting.transaction_id
        WHERE posting.account_id = ? AND tx.status = 'posted'
        """,
        (account_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return 0
    return int(row[0])


async def balances_for_accounts(
    conn: aiosqlite.Connection, account_ids: list[int]
) -> dict[int, int]:
    """Return signed posted balances keyed by each requested account identifier."""
    if not account_ids:
        return {}

    placeholders = ", ".join("?" for _ in account_ids)
    cursor = await conn.execute(
        f"""
        SELECT posting.account_id, SUM(posting.amount_paise)
        FROM ledger_postings AS posting
        JOIN ledger_transactions AS tx ON tx.id = posting.transaction_id
        WHERE posting.account_id IN ({placeholders}) AND tx.status = 'posted'
        GROUP BY posting.account_id
        """,  # noqa: S608
        tuple(account_ids),
    )
    balances = {int(account_id): int(balance) for account_id, balance in await cursor.fetchall()}
    return {account_id: balances.get(account_id, 0) for account_id in account_ids}


async def net_worth_totals(
    conn: aiosqlite.Connection, *, as_of: date | None = None
) -> tuple[int, int, int]:
    """Return assets, liabilities, and net worth from posted ledger balances."""
    as_of_clause = "" if as_of is None else " AND tx.date <= ?"
    cursor = await conn.execute(
        f"""
        SELECT
            COALESCE(SUM(
                CASE WHEN account.account_class LIKE 'asset_%'
                    THEN posting.amount_paise ELSE 0 END
            ), 0),
            COALESCE(SUM(
                CASE WHEN account.account_class LIKE 'liability_%'
                    THEN -posting.amount_paise ELSE 0 END
            ), 0)
        FROM ledger_postings AS posting
        JOIN ledger_transactions AS tx ON tx.id = posting.transaction_id
        JOIN accounts AS account ON account.id = posting.account_id
        WHERE tx.status = 'posted'{as_of_clause}
        """,
        () if as_of is None else (as_of.isoformat(),),
    )
    row = await cursor.fetchone()
    if row is None:
        return 0, 0, 0
    assets, liabilities = int(row[0]), int(row[1])
    return assets, liabilities, assets - liabilities
