"""Repository for email_transaction_staging table."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiosqlite


@dataclass(frozen=True, slots=True)
class StagedEmailRow:
    id: int
    gmail_message_id: str
    email_date: str
    email_subject: str | None
    email_from: str | None
    raw_snippet: str | None
    parsed_date: str | None
    parsed_amount_paise: int | None
    parsed_merchant: str | None
    parsed_category: str | None
    parsed_payment_mode: str | None
    parsed_transaction_type: str | None
    suggested_account_id: int | None
    status: str
    created_transaction_id: int | None
    created_at: str


_SELECT = """
    SELECT id, gmail_message_id, email_date, email_subject, email_from,
           raw_snippet, parsed_date, parsed_amount_paise, parsed_merchant,
           parsed_category, parsed_payment_mode, parsed_transaction_type,
           suggested_account_id, status, created_transaction_id, created_at
    FROM email_transaction_staging
"""


def _row(r: tuple[Any, ...]) -> StagedEmailRow:
    return StagedEmailRow(
        id=int(r[0]),
        gmail_message_id=str(r[1]),
        email_date=str(r[2]),
        email_subject=r[3],
        email_from=r[4],
        raw_snippet=r[5],
        parsed_date=r[6],
        parsed_amount_paise=int(r[7]) if r[7] is not None else None,
        parsed_merchant=r[8],
        parsed_category=r[9],
        parsed_payment_mode=r[10],
        parsed_transaction_type=r[11],
        suggested_account_id=int(r[12]) if r[12] is not None else None,
        status=str(r[13]),
        created_transaction_id=int(r[14]) if r[14] is not None else None,
        created_at=str(r[15]),
    )


async def list_staged(
    conn: aiosqlite.Connection,
    *,
    status: str | None = None,
    limit: int = 200,
) -> list[StagedEmailRow]:
    if status:
        cur = await conn.execute(
            _SELECT + " WHERE status = ? ORDER BY email_date DESC LIMIT ?",
            (status, limit),
        )
    else:
        cur = await conn.execute(
            _SELECT + " ORDER BY email_date DESC LIMIT ?",
            (limit,),
        )
    return [_row(r) for r in await cur.fetchall()]


async def get_staged(conn: aiosqlite.Connection, item_id: int) -> StagedEmailRow | None:
    cur = await conn.execute(_SELECT + " WHERE id = ?", (item_id,))
    r = await cur.fetchone()
    return _row(r) if r else None


async def get_by_gmail_id(
    conn: aiosqlite.Connection, gmail_message_id: str
) -> StagedEmailRow | None:
    cur = await conn.execute(
        _SELECT + " WHERE gmail_message_id = ?", (gmail_message_id,)
    )
    r = await cur.fetchone()
    return _row(r) if r else None


async def insert_staged(
    conn: aiosqlite.Connection,
    *,
    gmail_message_id: str,
    email_date: str,
    email_subject: str | None,
    email_from: str | None,
    raw_snippet: str | None,
    parsed_date: str | None,
    parsed_amount_paise: int | None,
    parsed_merchant: str | None,
    parsed_category: str | None,
    parsed_payment_mode: str | None,
    parsed_transaction_type: str | None,
) -> int | None:
    """Insert a new staged item. Returns id, or None if gmail_message_id already exists."""
    try:
        cur = await conn.execute(
            """
            INSERT INTO email_transaction_staging (
                gmail_message_id, email_date, email_subject, email_from, raw_snippet,
                parsed_date, parsed_amount_paise, parsed_merchant, parsed_category,
                parsed_payment_mode, parsed_transaction_type
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                gmail_message_id, email_date, email_subject, email_from, raw_snippet,
                parsed_date, parsed_amount_paise, parsed_merchant, parsed_category,
                parsed_payment_mode, parsed_transaction_type,
            ),
        )
        await conn.commit()
        return cur.lastrowid
    except aiosqlite.IntegrityError:
        return None  # duplicate gmail_message_id


async def update_staged(
    conn: aiosqlite.Connection,
    item_id: int,
    *,
    parsed_date: str | None = None,
    parsed_amount_paise: int | None = None,
    parsed_merchant: str | None = None,
    parsed_category: str | None = None,
    parsed_payment_mode: str | None = None,
    parsed_transaction_type: str | None = None,
    suggested_account_id: int | None = None,
) -> None:
    await conn.execute(
        """
        UPDATE email_transaction_staging SET
            parsed_date = ?, parsed_amount_paise = ?, parsed_merchant = ?,
            parsed_category = ?, parsed_payment_mode = ?,
            parsed_transaction_type = ?, suggested_account_id = ?
        WHERE id = ?
        """,
        (
            parsed_date, parsed_amount_paise, parsed_merchant, parsed_category,
            parsed_payment_mode, parsed_transaction_type, suggested_account_id,
            item_id,
        ),
    )
    await conn.commit()


async def set_status(
    conn: aiosqlite.Connection,
    item_id: int,
    status: str,
    *,
    created_transaction_id: int | None = None,
) -> None:
    await conn.execute(
        "UPDATE email_transaction_staging SET status = ?, created_transaction_id = ? WHERE id = ?",
        (status, created_transaction_id, item_id),
    )
    await conn.commit()


async def delete_by_status(conn: aiosqlite.Connection, status: str) -> int:
    cur = await conn.execute(
        "DELETE FROM email_transaction_staging WHERE status = ?", (status,)
    )
    await conn.commit()
    return cur.rowcount or 0


async def count_by_status(conn: aiosqlite.Connection) -> dict[str, int]:
    cur = await conn.execute(
        "SELECT status, COUNT(*) FROM email_transaction_staging GROUP BY status"
    )
    rows = await cur.fetchall()
    return {str(r[0]): int(r[1]) for r in rows}
