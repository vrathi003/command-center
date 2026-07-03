"""Credit cards and uploaded statements."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiosqlite


@dataclass(frozen=True, slots=True)
class CreditCardRow:
    id: int
    name: str
    issuer: str | None
    last_four: str | None
    credit_limit_paise: int
    current_balance_paise: int | None
    notes: str | None
    is_active: bool
    account_id: int | None = None
    statement_day: int | None = None
    due_day: int | None = None
    minimum_due_pct: float | None = None
    reward_rate_pct: float | None = None


@dataclass(frozen=True, slots=True)
class CreditCardStatementRow:
    id: int
    credit_card_id: int
    filename: str
    period_start: str | None
    period_end: str | None
    extraction_preview: str | None
    summary_json: str | None
    line_items_json: str | None
    status: str
    created_at: str | None


def _card_from_tuple(r: tuple[Any, ...]) -> CreditCardRow:
    return CreditCardRow(
        id=int(r[0]),
        name=str(r[1]),
        issuer=str(r[2]) if r[2] is not None else None,
        last_four=str(r[3]) if r[3] is not None else None,
        credit_limit_paise=int(r[4]),
        current_balance_paise=int(r[5]) if r[5] is not None else None,
        notes=str(r[6]) if r[6] is not None else None,
        is_active=bool(int(r[7])),
        account_id=int(r[8]) if len(r) > 8 and r[8] is not None else None,
        statement_day=int(r[9]) if len(r) > 9 and r[9] is not None else None,
        due_day=int(r[10]) if len(r) > 10 and r[10] is not None else None,
        minimum_due_pct=float(r[11]) if len(r) > 11 and r[11] is not None else None,
        reward_rate_pct=float(r[12]) if len(r) > 12 and r[12] is not None else None,
    )


def _stmt_from_tuple(r: tuple[Any, ...]) -> CreditCardStatementRow:
    return CreditCardStatementRow(
        id=int(r[0]),
        credit_card_id=int(r[1]),
        filename=str(r[2]),
        period_start=str(r[3]) if r[3] is not None else None,
        period_end=str(r[4]) if r[4] is not None else None,
        extraction_preview=str(r[5]) if r[5] is not None else None,
        summary_json=str(r[6]) if r[6] is not None else None,
        line_items_json=str(r[7]) if r[7] is not None else None,
        status=str(r[8]),
        created_at=str(r[9]) if len(r) > 9 and r[9] is not None else None,
    )


async def list_credit_cards(
    conn: aiosqlite.Connection,
    *,
    active_only: bool = False,
) -> list[CreditCardRow]:
    if active_only:
        cur = await conn.execute(
            """
            SELECT id, name, issuer, last_four, credit_limit_paise, current_balance_paise,
                   notes, is_active, account_id, statement_day, due_day,
                   minimum_due_pct, reward_rate_pct
            FROM credit_cards WHERE is_active = 1 ORDER BY name
            """,
        )
    else:
        cur = await conn.execute(
            """
            SELECT id, name, issuer, last_four, credit_limit_paise, current_balance_paise,
                   notes, is_active, account_id, statement_day, due_day,
                   minimum_due_pct, reward_rate_pct
            FROM credit_cards ORDER BY is_active DESC, name
            """,
        )
    rows = await cur.fetchall()
    return [_card_from_tuple(tuple(x)) for x in rows]


async def get_credit_card(conn: aiosqlite.Connection, card_id: int) -> CreditCardRow | None:
    cur = await conn.execute(
        """
        SELECT id, name, issuer, last_four, credit_limit_paise, current_balance_paise,
               notes, is_active, account_id, statement_day, due_day,
               minimum_due_pct, reward_rate_pct
        FROM credit_cards WHERE id = ?
        """,
        (card_id,),
    )
    r = await cur.fetchone()
    return _card_from_tuple(tuple(r)) if r else None


async def insert_credit_card(
    conn: aiosqlite.Connection,
    *,
    name: str,
    issuer: str | None,
    last_four: str | None,
    credit_limit_paise: int,
    current_balance_paise: int | None,
    notes: str | None,
    is_active: bool = True,
    account_id: int | None = None,
    statement_day: int | None = None,
    due_day: int | None = None,
    minimum_due_pct: float | None = None,
    reward_rate_pct: float | None = None,
) -> int:
    cur = await conn.execute(
        """
        INSERT INTO credit_cards (
            name, issuer, last_four, credit_limit_paise,
            current_balance_paise, notes, is_active,
            account_id, statement_day, due_day, minimum_due_pct, reward_rate_pct,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            name,
            issuer,
            last_four,
            credit_limit_paise,
            current_balance_paise,
            notes,
            1 if is_active else 0,
            account_id,
            statement_day,
            due_day,
            minimum_due_pct,
            reward_rate_pct,
        ),
    )
    await conn.commit()
    last = cur.lastrowid
    if last is None:
        msg = "INSERT INTO credit_cards did not set lastrowid"
        raise RuntimeError(msg)
    return int(last)


async def update_credit_card_row(conn: aiosqlite.Connection, row: CreditCardRow) -> None:
    await conn.execute(
        """
        UPDATE credit_cards SET
            name = ?, issuer = ?, last_four = ?, credit_limit_paise = ?,
            current_balance_paise = ?, notes = ?, is_active = ?,
            account_id = ?, statement_day = ?, due_day = ?,
            minimum_due_pct = ?, reward_rate_pct = ?,
            updated_at = datetime('now')
        WHERE id = ?
        """,
        (
            row.name,
            row.issuer,
            row.last_four,
            row.credit_limit_paise,
            row.current_balance_paise,
            row.notes,
            1 if row.is_active else 0,
            row.account_id,
            row.statement_day,
            row.due_day,
            row.minimum_due_pct,
            row.reward_rate_pct,
            row.id,
        ),
    )
    await conn.commit()


async def set_account_id(
    conn: aiosqlite.Connection,
    card_id: int,
    account_id: int,
) -> None:
    await conn.execute(
        "UPDATE credit_cards SET account_id = ?, updated_at = datetime('now') WHERE id = ?",
        (account_id, card_id),
    )
    await conn.commit()


async def total_outstanding_balance(conn: aiosqlite.Connection) -> int:
    """Sum of current_balance_paise across all active credit cards (for net worth liabilities)."""
    cur = await conn.execute(
        """
        SELECT COALESCE(SUM(current_balance_paise), 0)
        FROM credit_cards
        WHERE is_active = 1 AND current_balance_paise > 0
        """
    )
    r = await cur.fetchone()
    return int(r[0]) if r else 0


async def find_card_account_id_by_last_four(
    conn: aiosqlite.Connection,
    last_four: str,
    issuer_hint: str | None = None,
) -> int | None:
    """Return account_id of the active CC matching last_four (and optionally issuer)."""
    if issuer_hint:
        cur = await conn.execute(
            """
            SELECT account_id FROM credit_cards
            WHERE last_four = ? AND is_active = 1 AND account_id IS NOT NULL
              AND LOWER(issuer) LIKE ?
            LIMIT 1
            """,
            (last_four, f"%{issuer_hint.lower()}%"),
        )
        r = await cur.fetchone()
        if r:
            return int(r[0])
    # Fallback: match by last_four only
    cur = await conn.execute(
        """
        SELECT account_id FROM credit_cards
        WHERE last_four = ? AND is_active = 1 AND account_id IS NOT NULL
        LIMIT 1
        """,
        (last_four,),
    )
    r = await cur.fetchone()
    return int(r[0]) if r else None


async def delete_credit_card(conn: aiosqlite.Connection, card_id: int) -> bool:
    cur = await conn.execute("DELETE FROM credit_cards WHERE id = ?", (card_id,))
    await conn.commit()
    return cur.rowcount > 0


async def list_statements_for_card(
    conn: aiosqlite.Connection,
    card_id: int,
) -> list[CreditCardStatementRow]:
    cur = await conn.execute(
        """
        SELECT id, credit_card_id, filename, period_start, period_end, extraction_preview,
               summary_json, line_items_json, status, created_at
        FROM credit_card_statements
        WHERE credit_card_id = ?
        ORDER BY datetime(created_at) DESC, id DESC
        """,
        (card_id,),
    )
    rows = await cur.fetchall()
    return [_stmt_from_tuple(tuple(x)) for x in rows]


async def get_statement(
    conn: aiosqlite.Connection,
    statement_id: int,
) -> CreditCardStatementRow | None:
    cur = await conn.execute(
        """
        SELECT id, credit_card_id, filename, period_start, period_end, extraction_preview,
               summary_json, line_items_json, status, created_at
        FROM credit_card_statements WHERE id = ?
        """,
        (statement_id,),
    )
    r = await cur.fetchone()
    return _stmt_from_tuple(tuple(r)) if r else None


async def insert_statement(
    conn: aiosqlite.Connection,
    *,
    credit_card_id: int,
    filename: str,
    period_start: str | None,
    period_end: str | None,
    extraction_preview: str | None,
    summary_json: str | None,
    line_items_json: str | None,
    status: str = "pending_review",
) -> int:
    cur = await conn.execute(
        """
        INSERT INTO credit_card_statements (
            credit_card_id, filename, period_start, period_end, extraction_preview,
            summary_json, line_items_json, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            credit_card_id,
            filename,
            period_start,
            period_end,
            extraction_preview,
            summary_json,
            line_items_json,
            status,
        ),
    )
    await conn.commit()
    last = cur.lastrowid
    if last is None:
        msg = "INSERT INTO credit_card_statements did not set lastrowid"
        raise RuntimeError(msg)
    return int(last)


async def update_statement_status(
    conn: aiosqlite.Connection,
    statement_id: int,
    *,
    status: str,
) -> None:
    await conn.execute(
        "UPDATE credit_card_statements SET status = ? WHERE id = ?",
        (status, statement_id),
    )
    await conn.commit()


async def delete_statement(conn: aiosqlite.Connection, statement_id: int) -> bool:
    cur = await conn.execute("DELETE FROM credit_card_statements WHERE id = ?", (statement_id,))
    await conn.commit()
    return cur.rowcount > 0


@dataclass(frozen=True, slots=True)
class CreditCardEmiRow:
    id: int
    credit_card_id: int
    description: str
    limit_blocked_paise: int
    emi_amount_paise: int
    tenure_months: int
    installments_paid: int
    is_active: bool
    notes: str | None
    loan_type: str | None
    creation_date: str | None
    finish_date: str | None
    principal_paise: int | None
    outstanding_instalment_paise: int | None
    created_at: str | None
    updated_at: str | None


def _emi_from_tuple(r: tuple[Any, ...]) -> CreditCardEmiRow:
    return CreditCardEmiRow(
        id=int(r[0]),
        credit_card_id=int(r[1]),
        description=str(r[2]),
        limit_blocked_paise=int(r[3]),
        emi_amount_paise=int(r[4]),
        tenure_months=int(r[5]),
        installments_paid=int(r[6]),
        is_active=bool(int(r[7])),
        notes=str(r[8]) if r[8] is not None else None,
        loan_type=str(r[9]) if len(r) > 9 and r[9] is not None else None,
        creation_date=str(r[10]) if len(r) > 10 and r[10] is not None else None,
        finish_date=str(r[11]) if len(r) > 11 and r[11] is not None else None,
        principal_paise=int(r[12]) if len(r) > 12 and r[12] is not None else None,
        outstanding_instalment_paise=int(r[13]) if len(r) > 13 and r[13] is not None else None,
        created_at=str(r[14]) if len(r) > 14 and r[14] is not None else None,
        updated_at=str(r[15]) if len(r) > 15 and r[15] is not None else None,
    )


async def emi_totals_by_card(
    conn: aiosqlite.Connection,
) -> dict[int, tuple[int, int, int]]:
    """Per card: (limit_blocked_sum, monthly_emi_sum, active_plan_count)."""
    cur = await conn.execute(
        """
        SELECT credit_card_id,
            COALESCE(SUM(
                CASE WHEN is_active = 1 AND installments_paid < tenure_months
                THEN limit_blocked_paise ELSE 0 END
            ), 0),
            COALESCE(SUM(
                CASE WHEN is_active = 1 AND installments_paid < tenure_months
                THEN emi_amount_paise ELSE 0 END
            ), 0),
            COALESCE(SUM(
                CASE WHEN is_active = 1 AND installments_paid < tenure_months
                THEN 1 ELSE 0 END
            ), 0)
        FROM credit_card_emis
        GROUP BY credit_card_id
        """,
    )
    rows = await cur.fetchall()
    out: dict[int, tuple[int, int, int]] = {}
    for r in rows:
        out[int(r[0])] = (int(r[1]), int(r[2]), int(r[3]))
    return out


async def list_emis_for_card(
    conn: aiosqlite.Connection,
    card_id: int,
) -> list[CreditCardEmiRow]:
    cur = await conn.execute(
        """
        SELECT id, credit_card_id, description, limit_blocked_paise, emi_amount_paise,
               tenure_months, installments_paid, is_active, notes,
               loan_type, creation_date, finish_date, principal_paise, outstanding_instalment_paise,
               created_at, updated_at
        FROM credit_card_emis
        WHERE credit_card_id = ?
        ORDER BY id ASC
        """,
        (card_id,),
    )
    rows = await cur.fetchall()
    return [_emi_from_tuple(tuple(x)) for x in rows]


async def get_emi(
    conn: aiosqlite.Connection,
    emi_id: int,
) -> CreditCardEmiRow | None:
    cur = await conn.execute(
        """
        SELECT id, credit_card_id, description, limit_blocked_paise, emi_amount_paise,
               tenure_months, installments_paid, is_active, notes,
               loan_type, creation_date, finish_date, principal_paise, outstanding_instalment_paise,
               created_at, updated_at
        FROM credit_card_emis WHERE id = ?
        """,
        (emi_id,),
    )
    r = await cur.fetchone()
    return _emi_from_tuple(tuple(r)) if r else None


async def insert_emi(
    conn: aiosqlite.Connection,
    *,
    credit_card_id: int,
    description: str,
    limit_blocked_paise: int,
    emi_amount_paise: int,
    tenure_months: int,
    installments_paid: int,
    is_active: bool,
    notes: str | None,
    loan_type: str | None = None,
    creation_date: str | None = None,
    finish_date: str | None = None,
    principal_paise: int | None = None,
    outstanding_instalment_paise: int | None = None,
) -> int:
    cur = await conn.execute(
        """
        INSERT INTO credit_card_emis (
            credit_card_id, description, limit_blocked_paise, emi_amount_paise,
            tenure_months, installments_paid, is_active, notes,
            loan_type, creation_date, finish_date, principal_paise, outstanding_instalment_paise,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            credit_card_id,
            description.strip(),
            limit_blocked_paise,
            emi_amount_paise,
            tenure_months,
            installments_paid,
            1 if is_active else 0,
            notes.strip() if notes else None,
            loan_type,
            creation_date,
            finish_date,
            principal_paise,
            outstanding_instalment_paise,
        ),
    )
    await conn.commit()
    last = cur.lastrowid
    if last is None:
        msg = "INSERT INTO credit_card_emis did not set lastrowid"
        raise RuntimeError(msg)
    return int(last)


async def update_emi_row(conn: aiosqlite.Connection, row: CreditCardEmiRow) -> None:
    await conn.execute(
        """
        UPDATE credit_card_emis SET
            description = ?, limit_blocked_paise = ?, emi_amount_paise = ?,
            tenure_months = ?, installments_paid = ?, is_active = ?, notes = ?,
            loan_type = ?, creation_date = ?, finish_date = ?,
            principal_paise = ?, outstanding_instalment_paise = ?,
            updated_at = datetime('now')
        WHERE id = ?
        """,
        (
            row.description,
            row.limit_blocked_paise,
            row.emi_amount_paise,
            row.tenure_months,
            row.installments_paid,
            1 if row.is_active else 0,
            row.notes,
            row.loan_type,
            row.creation_date,
            row.finish_date,
            row.principal_paise,
            row.outstanding_instalment_paise,
            row.id,
        ),
    )
    await conn.commit()


async def delete_emi(conn: aiosqlite.Connection, emi_id: int) -> bool:
    cur = await conn.execute("DELETE FROM credit_card_emis WHERE id = ?", (emi_id,))
    await conn.commit()
    return cur.rowcount > 0
