"""Transaction persistence and aggregates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import uuid4

import aiosqlite

from finance_common.types import Category, Paise, PaymentMode

# Exclude internal transfers from spend/category totals (silent double-counting).
_SPEND_SQL = """
        is_deleted = 0
        AND (transaction_type IS NULL OR transaction_type != 'transfer')
"""


@dataclass(frozen=True, slots=True)
class TransactionRow:
    id: int
    date: str
    amount_paise: int
    category: str
    merchant: str | None
    payment_mode: str
    account: str | None
    notes: str | None
    transaction_type: str
    source: str
    discord_message_id: str | None
    account_id: int | None
    transfer_pair_id: str | None
    tags: str | None


async def insert_transaction(
    conn: aiosqlite.Connection,
    *,
    tx_date: date,
    amount_paise: Paise,
    category: str,
    merchant: str | None,
    payment_mode: str,
    account: str | None,
    notes: str | None,
    source: str,
    transaction_type: str = "debit",
    discord_message_id: str | None = None,
    account_id: int | None = None,
    transfer_pair_id: str | None = None,
    tags: str | None = None,
) -> int:
    """Insert a transaction and return its id."""
    cur = await conn.execute(
        """
        INSERT INTO transactions (
            date, amount_paise, category, merchant, payment_mode, account, notes,
            transaction_type, source, discord_message_id, account_id, transfer_pair_id, tags,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            tx_date.isoformat(),
            int(amount_paise),
            category,
            merchant,
            payment_mode,
            account,
            notes,
            transaction_type,
            source,
            discord_message_id,
            account_id,
            transfer_pair_id,
            tags,
        ),
    )
    await conn.commit()
    last = cur.lastrowid
    if last is None:
        msg = "INSERT INTO transactions did not set lastrowid"
        raise RuntimeError(msg)
    return int(last)


async def insert_transfer_pair(
    conn: aiosqlite.Connection,
    *,
    amount_paise: int,
    tx_date: date,
    from_account_id: int,
    to_account_id: int,
    from_account_name: str,
    to_account_name: str,
    notes: str | None,
    tags: str | None,
    source: str,
    pair_id: str | None = None,
    discord_message_id: str | None = None,
) -> tuple[int, int, str]:
    """Insert two linked transfer rows atomically. Returns (out_id, in_id, pair_id)."""
    pid = pair_id or str(uuid4())
    cat = Category.TRANSFER.value
    pm = PaymentMode.BANK_TRANSFER.value
    await conn.execute("BEGIN IMMEDIATE")
    try:
        cur1 = await conn.execute(
            """
            INSERT INTO transactions (
                date, amount_paise, category, merchant, payment_mode, account, notes,
                transaction_type, source, discord_message_id, account_id, transfer_pair_id, tags,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                tx_date.isoformat(),
                amount_paise,
                cat,
                "Transfer out",
                pm,
                from_account_name,
                notes,
                "transfer",
                source,
                discord_message_id,
                from_account_id,
                pid,
                tags,
            ),
        )
        id1 = cur1.lastrowid
        cur2 = await conn.execute(
            """
            INSERT INTO transactions (
                date, amount_paise, category, merchant, payment_mode, account, notes,
                transaction_type, source, discord_message_id, account_id, transfer_pair_id, tags,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                tx_date.isoformat(),
                amount_paise,
                cat,
                "Transfer in",
                pm,
                to_account_name,
                notes,
                "transfer",
                source,
                discord_message_id,
                to_account_id,
                pid,
                tags,
            ),
        )
        id2 = cur2.lastrowid
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise
    if id1 is None or id2 is None:
        msg = "transfer insert did not set lastrowid"
        raise RuntimeError(msg)
    return int(id1), int(id2), pid


async def soft_delete_last(conn: aiosqlite.Connection, *, source: str) -> int | None:
    """Mark the most recent non-deleted row from `source` as deleted.

    Transfer pairs are both deleted.
    """
    cur = await conn.execute(
        """
        SELECT id, transfer_pair_id FROM transactions
        WHERE is_deleted = 0 AND source = ?
        ORDER BY datetime(created_at) DESC, id DESC
        LIMIT 1
        """,
        (source,),
    )
    row = await cur.fetchone()
    if row is None:
        return None
    tid = int(row[0])
    pair_id = row[1]
    if pair_id:
        await conn.execute(
            """
            UPDATE transactions SET is_deleted = 1, updated_at = datetime('now')
            WHERE is_deleted = 0 AND transfer_pair_id = ?
            """,
            (pair_id,),
        )
    else:
        await conn.execute(
            "UPDATE transactions SET is_deleted = 1, updated_at = datetime('now') WHERE id = ?",
            (tid,),
        )
    await conn.commit()
    return tid


async def sum_between(
    conn: aiosqlite.Connection,
    *,
    start: date,
    end: date,
) -> int:
    """Total spend (paise) in [start, end] inclusive, excluding deleted rows and transfers."""
    cur = await conn.execute(
        f"""
        SELECT COALESCE(SUM(amount_paise), 0) FROM transactions
        WHERE {_SPEND_SQL}
          AND date >= ? AND date <= ?
        """,
        (start.isoformat(), end.isoformat()),
    )
    row = await cur.fetchone()
    return int(row[0]) if row else 0


async def sum_by_category_month(
    conn: aiosqlite.Connection,
    *,
    start: date,
    end: date,
) -> dict[str, int]:
    """Spend per category (paise) in range; excludes transfers."""
    cur = await conn.execute(
        f"""
        SELECT category, COALESCE(SUM(amount_paise), 0) FROM transactions
        WHERE {_SPEND_SQL} AND date >= ? AND date <= ?
        GROUP BY category
        ORDER BY category
        """,
        (start.isoformat(), end.isoformat()),
    )
    rows = list(await cur.fetchall())
    return {str(r[0]): int(r[1]) for r in rows}


_TX_SELECT_COLS = (
    "id, date, amount_paise, category, merchant, payment_mode, account, notes, "
    "transaction_type, source, discord_message_id, account_id, transfer_pair_id, tags"
)


def _row_to_tx(r: tuple[Any, ...]) -> TransactionRow:
    return TransactionRow(
        id=int(r[0]),
        date=str(r[1]),
        amount_paise=int(r[2]),
        category=str(r[3]),
        merchant=str(r[4]) if r[4] is not None else None,
        payment_mode=str(r[5]),
        account=str(r[6]) if r[6] is not None else None,
        notes=str(r[7]) if r[7] is not None else None,
        transaction_type=str(r[8]) if r[8] else "debit",
        source=str(r[9]),
        discord_message_id=str(r[10]) if r[10] is not None else None,
        account_id=int(r[11]) if r[11] is not None else None,
        transfer_pair_id=str(r[12]) if r[12] is not None else None,
        tags=str(r[13]) if r[13] is not None else None,
    )


async def get_by_id(conn: aiosqlite.Connection, tx_id: int) -> TransactionRow | None:
    cur = await conn.execute(
        f"""
        SELECT {_TX_SELECT_COLS}
        FROM transactions
        WHERE id = ? AND is_deleted = 0
        """,
        (tx_id,),
    )
    r = await cur.fetchone()
    if r is None:
        return None
    return _row_to_tx(tuple(r))


async def get_transfer_pair_sibling(
    conn: aiosqlite.Connection, *, pair_id: str, exclude_id: int
) -> TransactionRow | None:
    """The other non-deleted leg of a transfer pair, if any."""
    cur = await conn.execute(
        f"""
        SELECT {_TX_SELECT_COLS}
        FROM transactions
        WHERE transfer_pair_id = ? AND is_deleted = 0 AND id != ?
        LIMIT 1
        """,
        (pair_id, exclude_id),
    )
    r = await cur.fetchone()
    if r is None:
        return None
    return _row_to_tx(tuple(r))


async def soft_delete_by_id(conn: aiosqlite.Connection, tx_id: int) -> bool:
    """Soft-delete by id. If the row is part of a transfer pair, deletes both legs."""
    cur = await conn.execute(
        """
        SELECT transfer_pair_id FROM transactions WHERE id = ? AND is_deleted = 0
        """,
        (tx_id,),
    )
    row = await cur.fetchone()
    if row is None:
        return False
    pair_id = row[0]
    if pair_id:
        cur = await conn.execute(
            """
            UPDATE transactions SET is_deleted = 1, updated_at = datetime('now')
            WHERE is_deleted = 0 AND transfer_pair_id = ?
            """,
            (pair_id,),
        )
    else:
        cur = await conn.execute(
            """
            UPDATE transactions SET is_deleted = 1, updated_at = datetime('now')
            WHERE id = ? AND is_deleted = 0
            """,
            (tx_id,),
        )
    await conn.commit()
    return cur.rowcount > 0


async def soft_delete_by_ids(conn: aiosqlite.Connection, ids: list[int]) -> int:
    """Soft-delete many ids. Returns number of rows updated."""
    if not ids:
        return 0
    placeholders = ",".join("?" * len(ids))
    cur = await conn.execute(
        f"""
        UPDATE transactions SET is_deleted = 1, updated_at = datetime('now')
        WHERE is_deleted = 0 AND id IN ({placeholders})
        """,
        tuple(ids),
    )
    await conn.commit()
    return int(cur.rowcount)


async def update_transaction_fields(
    conn: aiosqlite.Connection,
    tx_id: int,
    *,
    tx_date: date,
    amount_paise: int,
    category: str,
    merchant: str | None,
    payment_mode: str,
    notes: str | None,
    source_must_be: str | None = None,
) -> bool:
    """Update a transaction row. If ``source_must_be`` is set, only rows with that source match."""
    if source_must_be is None:
        cur = await conn.execute(
            """
            UPDATE transactions SET
                date = ?, amount_paise = ?, category = ?, merchant = ?,
                payment_mode = ?, notes = ?, updated_at = datetime('now')
            WHERE id = ? AND is_deleted = 0
            """,
            (
                tx_date.isoformat(),
                amount_paise,
                category,
                merchant,
                payment_mode,
                notes,
                tx_id,
            ),
        )
    else:
        cur = await conn.execute(
            """
            UPDATE transactions SET
                date = ?, amount_paise = ?, category = ?, merchant = ?,
                payment_mode = ?, notes = ?, updated_at = datetime('now')
            WHERE id = ? AND is_deleted = 0 AND source = ?
            """,
            (
                tx_date.isoformat(),
                amount_paise,
                category,
                merchant,
                payment_mode,
                notes,
                tx_id,
                source_must_be,
            ),
        )
    await conn.commit()
    return cur.rowcount > 0


async def update_dashboard_debit_credit(
    conn: aiosqlite.Connection,
    tx_id: int,
    *,
    tx_date: date,
    amount_paise: int,
    category: str,
    merchant: str | None,
    payment_mode: str,
    notes: str | None,
    transaction_type: str,
    account: str | None,
    account_id: int | None,
    tags: str | None,
) -> bool:
    """Update a non-transfer row from the dashboard (full field set including account and type)."""
    cur = await conn.execute(
        """
        UPDATE transactions SET
            date = ?, amount_paise = ?, category = ?, merchant = ?,
            payment_mode = ?, notes = ?, transaction_type = ?,
            account = ?, account_id = ?, tags = ?, updated_at = datetime('now')
        WHERE id = ? AND is_deleted = 0
          AND (transaction_type IS NULL OR transaction_type != 'transfer')
        """,
        (
            tx_date.isoformat(),
            amount_paise,
            category,
            merchant,
            payment_mode,
            notes,
            transaction_type,
            account,
            account_id,
            tags,
            tx_id,
        ),
    )
    await conn.commit()
    return cur.rowcount > 0


async def update_transfer_pair_dashboard(
    conn: aiosqlite.Connection,
    *,
    pair_id: str,
    tx_date: date,
    amount_paise: int,
    from_account_id: int,
    to_account_id: int,
    from_account_name: str,
    to_account_name: str,
    notes: str | None,
    tags: str | None,
) -> bool:
    """Update both legs of a transfer (same pair_id, non-deleted).

    Resolves out/in legs by canonical ``Transfer out`` / ``Transfer in`` merchants when
    present; otherwise falls back to **ascending id** (matches ``insert_transfer_pair``
    insert order). Does not rely on merchant text alone so imports with ``transfer_pair_id``
    still update.
    """
    cat = Category.TRANSFER.value
    pm = PaymentMode.BANK_TRANSFER.value
    cur = await conn.execute(
        """
        SELECT id, merchant FROM transactions
        WHERE transfer_pair_id = ? AND is_deleted = 0
        ORDER BY id
        """,
        (pair_id,),
    )
    legs = [(int(r[0]), str(r[1]) if r[1] is not None else "") for r in await cur.fetchall()]
    if len(legs) != 2:
        return False
    (id1, m1), (id2, m2) = legs
    if m1 == "Transfer out" and m2 == "Transfer in":
        out_id, in_id = id1, id2
    elif m2 == "Transfer out" and m1 == "Transfer in":
        out_id, in_id = id2, id1
    else:
        out_id, in_id = id1, id2

    await conn.execute("BEGIN IMMEDIATE")
    try:
        cur1 = await conn.execute(
            """
            UPDATE transactions SET
                date = ?, amount_paise = ?, category = ?, merchant = ?,
                payment_mode = ?, account = ?, notes = ?, account_id = ?, tags = ?,
                updated_at = datetime('now')
            WHERE id = ? AND is_deleted = 0
            """,
            (
                tx_date.isoformat(),
                amount_paise,
                cat,
                "Transfer out",
                pm,
                from_account_name,
                notes,
                from_account_id,
                tags,
                out_id,
            ),
        )
        cur2 = await conn.execute(
            """
            UPDATE transactions SET
                date = ?, amount_paise = ?, category = ?, merchant = ?,
                payment_mode = ?, account = ?, notes = ?, account_id = ?, tags = ?,
                updated_at = datetime('now')
            WHERE id = ? AND is_deleted = 0
            """,
            (
                tx_date.isoformat(),
                amount_paise,
                cat,
                "Transfer in",
                pm,
                to_account_name,
                notes,
                to_account_id,
                tags,
                in_id,
            ),
        )
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise
    return (cur1.rowcount or 0) > 0 and (cur2.rowcount or 0) > 0


async def update_dashboard_transfer_orphan(
    conn: aiosqlite.Connection,
    tx_id: int,
    *,
    tx_date: date,
    amount_paise: int,
    category: str,
    merchant: str | None,
    payment_mode: str,
    notes: str | None,
    account: str | None,
    account_id: int | None,
    tags: str | None,
) -> bool:
    """Update a single ``transfer`` row with no ``transfer_pair_id`` (e.g. bank import)."""
    cur = await conn.execute(
        """
        UPDATE transactions SET
            date = ?, amount_paise = ?, category = ?, merchant = ?,
            payment_mode = ?, notes = ?, account = ?, account_id = ?, tags = ?,
            updated_at = datetime('now')
        WHERE id = ? AND is_deleted = 0
          AND transaction_type = 'transfer'
          AND transfer_pair_id IS NULL
        """,
        (
            tx_date.isoformat(),
            amount_paise,
            category,
            merchant,
            payment_mode,
            notes,
            account,
            account_id,
            tags,
            tx_id,
        ),
    )
    await conn.commit()
    return (cur.rowcount or 0) > 0


async def list_recent(
    conn: aiosqlite.Connection,
    *,
    limit: int = 10,
    start_date: str | None = None,
    end_date: str | None = None,
    account: str | None = None,
) -> list[TransactionRow]:
    clauses = ["is_deleted = 0"]
    params: list[object] = []
    if start_date:
        clauses.append("date >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("date <= ?")
        params.append(end_date)
    if account:
        clauses.append("account = ?")
        params.append(account)
    where = " AND ".join(clauses)
    params.append(limit)
    cur = await conn.execute(
        f"""
        SELECT {_TX_SELECT_COLS}
        FROM transactions
        WHERE {where}
        ORDER BY date DESC, id DESC
        LIMIT ?
        """,
        tuple(params),
    )
    rows = await cur.fetchall()
    return [_row_to_tx(tuple(r)) for r in rows]


async def sum_by_account(
    conn: aiosqlite.Connection,
    *,
    start: date,
    end: date,
) -> dict[str, int]:
    """Debit spend per account (paise) in range; excludes credits, transfers, deleted."""
    cur = await conn.execute(
        f"""
        SELECT COALESCE(account, 'Unknown'), COALESCE(SUM(amount_paise), 0)
        FROM transactions
        WHERE {_SPEND_SQL}
          AND transaction_type != 'credit'
          AND date >= ? AND date <= ?
        GROUP BY account
        ORDER BY account
        """,
        (start.isoformat(), end.isoformat()),
    )
    rows = list(await cur.fetchall())
    return {str(r[0]): int(r[1]) for r in rows}


async def list_accounts_with_transaction_count(
    conn: aiosqlite.Connection,
) -> list[dict[str, object]]:
    """Return distinct account names used in transactions with their tx count."""
    cur = await conn.execute(
        """
        SELECT account, COUNT(*) as tx_count
        FROM transactions
        WHERE is_deleted = 0 AND account IS NOT NULL AND account != ''
        GROUP BY account
        ORDER BY tx_count DESC
        """
    )
    rows = await cur.fetchall()
    return [{"account": str(r[0]), "tx_count": int(r[1])} for r in rows]
