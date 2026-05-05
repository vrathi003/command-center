"""CRUD for `transaction_templates` (quick-add presets)."""

from __future__ import annotations

from dataclasses import dataclass

import aiosqlite


@dataclass(frozen=True, slots=True)
class TemplateRow:
    id: int
    name: str
    amount: int | None
    merchant: str | None
    category: str | None
    account_id: int | None
    payment_mode: str | None
    transaction_type: str
    notes: str | None
    tags: str | None
    created_at: str
    is_deleted: bool


def _row(r: tuple[object, ...]) -> TemplateRow:
    return TemplateRow(
        id=int(r[0]),
        name=str(r[1]),
        amount=int(r[2]) if r[2] is not None else None,
        merchant=str(r[3]) if r[3] else None,
        category=str(r[4]) if r[4] else None,
        account_id=int(r[5]) if r[5] is not None else None,
        payment_mode=str(r[6]) if r[6] else None,
        transaction_type=str(r[7]) if r[7] else "debit",
        notes=str(r[8]) if r[8] else None,
        tags=str(r[9]) if r[9] else None,
        created_at=str(r[10]),
        is_deleted=bool(r[11]),
    )


async def list_templates(conn: aiosqlite.Connection) -> list[TemplateRow]:
    cur = await conn.execute(
        """
        SELECT id, name, amount, merchant, category, account_id, payment_mode,
               transaction_type, notes, tags, created_at, is_deleted
        FROM transaction_templates
        WHERE is_deleted = 0
        ORDER BY name COLLATE NOCASE
        """
    )
    rows = await cur.fetchall()
    return [_row(tuple(r)) for r in rows]


async def get_template(conn: aiosqlite.Connection, template_id: int) -> TemplateRow | None:
    cur = await conn.execute(
        """
        SELECT id, name, amount, merchant, category, account_id, payment_mode,
               transaction_type, notes, tags, created_at, is_deleted
        FROM transaction_templates
        WHERE id = ? AND is_deleted = 0
        """,
        (template_id,),
    )
    r = await cur.fetchone()
    return _row(tuple(r)) if r else None


async def create_template(
    conn: aiosqlite.Connection,
    *,
    name: str,
    amount: int | None,
    merchant: str | None,
    category: str | None,
    account_id: int | None,
    payment_mode: str | None,
    transaction_type: str,
    notes: str | None,
    tags: str | None,
) -> int:
    cur = await conn.execute(
        """
        INSERT INTO transaction_templates (
            name, amount, merchant, category, account_id, payment_mode,
            transaction_type, notes, tags
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name.strip(),
            amount,
            merchant,
            category,
            account_id,
            payment_mode,
            transaction_type,
            notes,
            tags,
        ),
    )
    await conn.commit()
    lid = cur.lastrowid
    if lid is None:
        msg = "INSERT transaction_templates did not set lastrowid"
        raise RuntimeError(msg)
    return int(lid)


async def update_template(
    conn: aiosqlite.Connection,
    template_id: int,
    *,
    name: str,
    amount: int | None,
    merchant: str | None,
    category: str | None,
    account_id: int | None,
    payment_mode: str | None,
    transaction_type: str,
    notes: str | None,
    tags: str | None,
) -> bool:
    cur = await conn.execute(
        """
        UPDATE transaction_templates SET
            name = ?, amount = ?, merchant = ?, category = ?, account_id = ?,
            payment_mode = ?, transaction_type = ?, notes = ?, tags = ?
        WHERE id = ? AND is_deleted = 0
        """,
        (
            name.strip(),
            amount,
            merchant,
            category,
            account_id,
            payment_mode,
            transaction_type,
            notes,
            tags,
            template_id,
        ),
    )
    await conn.commit()
    return cur.rowcount > 0


async def soft_delete_template(conn: aiosqlite.Connection, template_id: int) -> bool:
    cur = await conn.execute(
        """
        UPDATE transaction_templates SET is_deleted = 1
        WHERE id = ? AND is_deleted = 0
        """,
        (template_id,),
    )
    await conn.commit()
    return cur.rowcount > 0
