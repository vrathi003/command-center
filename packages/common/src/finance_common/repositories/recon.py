"""Persistence operations for reconciliation statements and confirmed matches."""

from __future__ import annotations

from datetime import date
from typing import cast

import aiosqlite

from finance_common.recon.models import (
    LineDirection,
    LineStatus,
    MatchMethod,
    NewStatement,
    NewStatementLine,
    ReconMatch,
    ReconStatement,
    ReconStatementLine,
    StatementStatus,
    StatementWorkspace,
)

_STATEMENT_COLUMNS = """
    id, account_id, period_start, period_end, opening_balance_paise,
    closing_balance_paise, status, source, filename, created_at, updated_at
"""
_LINE_COLUMNS = """
    id, statement_id, tx_date, amount_paise, direction, payee, narration,
    external_key, status, ignore_reason, created_at, updated_at
"""
_MATCH_COLUMNS = "id, line_id, ledger_transaction_id, method, confirmed_at"


def _statement_from_row(row: tuple[object, ...]) -> ReconStatement:
    return ReconStatement(
        id=int(row[0]),
        account_id=int(row[1]),
        period_start=date.fromisoformat(str(row[2])),
        period_end=date.fromisoformat(str(row[3])),
        opening_balance_paise=int(row[4]),
        closing_balance_paise=int(row[5]),
        status=cast(StatementStatus, str(row[6])),
        source=str(row[7]),
        filename=str(row[8]) if row[8] is not None else None,
        created_at=str(row[9]),
        updated_at=str(row[10]),
    )


def _line_from_row(row: tuple[object, ...]) -> ReconStatementLine:
    return ReconStatementLine(
        id=int(row[0]),
        statement_id=int(row[1]),
        tx_date=date.fromisoformat(str(row[2])),
        amount_paise=int(row[3]),
        direction=cast(LineDirection, str(row[4])),
        payee=str(row[5]) if row[5] is not None else None,
        narration=str(row[6]) if row[6] is not None else None,
        external_key=str(row[7]) if row[7] is not None else None,
        status=cast(LineStatus, str(row[8])),
        ignore_reason=str(row[9]) if row[9] is not None else None,
        created_at=str(row[10]),
        updated_at=str(row[11]),
    )


def _match_from_row(row: tuple[object, ...]) -> ReconMatch:
    return ReconMatch(
        id=int(row[0]),
        line_id=int(row[1]),
        ledger_transaction_id=int(row[2]),
        method=cast(MatchMethod, str(row[3])),
        confirmed_at=str(row[4]),
    )


async def create_statement(conn: aiosqlite.Connection, statement: NewStatement) -> int:
    """Create a statement workspace and return its identifier."""
    cursor = await conn.execute(
        """
        INSERT INTO recon_statements (
            account_id, period_start, period_end, opening_balance_paise,
            closing_balance_paise, source, filename
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            statement.account_id,
            statement.period_start.isoformat(),
            statement.period_end.isoformat(),
            statement.opening_balance_paise,
            statement.closing_balance_paise,
            statement.source,
            statement.filename,
        ),
    )
    await conn.commit()
    if cursor.lastrowid is None:
        raise RuntimeError("INSERT INTO recon_statements did not set lastrowid")
    return int(cursor.lastrowid)


async def insert_statement_lines(
    conn: aiosqlite.Connection,
    statement_id: int,
    lines: tuple[NewStatementLine, ...],
) -> list[int]:
    """Insert statement lines, reusing an existing line for an external key."""
    line_ids: list[int] = []
    for line in lines:
        if line.external_key is not None:
            cursor = await conn.execute(
                """
                SELECT id FROM recon_statement_lines
                WHERE statement_id = ? AND external_key = ?
                """,
                (statement_id, line.external_key),
            )
            existing = await cursor.fetchone()
            if existing is not None:
                line_ids.append(int(existing[0]))
                continue

        cursor = await conn.execute(
            """
            INSERT INTO recon_statement_lines (
                statement_id, tx_date, amount_paise, direction, payee, narration, external_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                statement_id,
                line.tx_date.isoformat(),
                line.amount_paise,
                line.direction,
                line.payee,
                line.narration,
                line.external_key,
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("INSERT INTO recon_statement_lines did not set lastrowid")
        line_ids.append(int(cursor.lastrowid))
    await conn.commit()
    return line_ids


async def list_statements_by_account(
    conn: aiosqlite.Connection, account_id: int
) -> list[ReconStatement]:
    """List an account's statements from newest period to oldest."""
    cursor = await conn.execute(
        f"""
        SELECT {_STATEMENT_COLUMNS}
        FROM recon_statements
        WHERE account_id = ?
        ORDER BY period_end DESC, period_start DESC, id DESC
        """,
        (account_id,),
    )
    return [_statement_from_row(row) for row in await cursor.fetchall()]


async def get_statement_workspace(
    conn: aiosqlite.Connection, statement_id: int
) -> StatementWorkspace | None:
    """Return persisted statement metadata, its lines, and confirmed matches."""
    statement_cursor = await conn.execute(
        f"SELECT {_STATEMENT_COLUMNS} FROM recon_statements WHERE id = ?",
        (statement_id,),
    )
    statement_row = await statement_cursor.fetchone()
    if statement_row is None:
        return None

    line_cursor = await conn.execute(
        f"""
        SELECT {_LINE_COLUMNS}
        FROM recon_statement_lines
        WHERE statement_id = ?
        ORDER BY tx_date, id
        """,
        (statement_id,),
    )
    match_cursor = await conn.execute(
        f"""
        SELECT {_MATCH_COLUMNS}
        FROM recon_matches
        WHERE line_id IN (
            SELECT id FROM recon_statement_lines WHERE statement_id = ?
        )
        ORDER BY line_id
        """,
        (statement_id,),
    )
    return StatementWorkspace(
        statement=_statement_from_row(statement_row),
        lines=tuple(_line_from_row(row) for row in await line_cursor.fetchall()),
        matches=tuple(_match_from_row(row) for row in await match_cursor.fetchall()),
    )


async def insert_match(
    conn: aiosqlite.Connection,
    *,
    line_id: int,
    ledger_transaction_id: int,
    method: MatchMethod,
) -> int:
    """Create one confirmed match for a statement line."""
    cursor = await conn.execute(
        """
        INSERT INTO recon_matches (line_id, ledger_transaction_id, method)
        VALUES (?, ?, ?)
        """,
        (line_id, ledger_transaction_id, method),
    )
    await conn.commit()
    if cursor.lastrowid is None:
        raise RuntimeError("INSERT INTO recon_matches did not set lastrowid")
    return int(cursor.lastrowid)


async def delete_match(conn: aiosqlite.Connection, line_id: int) -> bool:
    """Remove a statement line's confirmed match."""
    cursor = await conn.execute("DELETE FROM recon_matches WHERE line_id = ?", (line_id,))
    await conn.commit()
    return cursor.rowcount > 0


async def update_line_status(
    conn: aiosqlite.Connection,
    line_id: int,
    *,
    status: LineStatus,
    ignore_reason: str | None = None,
) -> bool:
    """Update a line's reconciliation status and optional ignore rationale."""
    cursor = await conn.execute(
        """
        UPDATE recon_statement_lines
        SET status = ?, ignore_reason = ?, updated_at = datetime('now')
        WHERE id = ?
        """,
        (status, ignore_reason, line_id),
    )
    await conn.commit()
    return cursor.rowcount > 0


async def set_statement_status(
    conn: aiosqlite.Connection,
    statement_id: int,
    *,
    status: StatementStatus,
) -> bool:
    """Set a statement's soft-close status."""
    cursor = await conn.execute(
        """
        UPDATE recon_statements
        SET status = ?, updated_at = datetime('now')
        WHERE id = ?
        """,
        (status, statement_id),
    )
    await conn.commit()
    return cursor.rowcount > 0
