from __future__ import annotations

from datetime import date
from pathlib import Path

import aiosqlite
import pytest

from finance_common.db import ensure_database
from finance_common.recon.models import NewStatement, NewStatementLine
from finance_common.repositories import recon


async def _account_id(conn: aiosqlite.Connection) -> int:
    cursor = await conn.execute(
        "INSERT INTO accounts (name, type, account_class) VALUES ('Bank', 'savings', 'asset_cash')"
    )
    await conn.commit()
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid)


@pytest.mark.asyncio
async def test_statement_repository_persists_workspace_and_match_lifecycle(tmp_path: Path) -> None:
    db = tmp_path / "recon.db"
    await ensure_database(db)

    async with aiosqlite.connect(db) as conn:
        account_id = await _account_id(conn)
        statement_id = await recon.create_statement(
            conn,
            NewStatement(
                account_id=account_id,
                period_start=date(2026, 8, 1),
                period_end=date(2026, 8, 31),
                opening_balance_paise=100_000,
                closing_balance_paise=75_000,
                source="upload",
                filename="august.csv",
            ),
        )
        line_ids = await recon.insert_statement_lines(
            conn,
            statement_id,
            (
                NewStatementLine(
                    tx_date=date(2026, 8, 10),
                    amount_paise=25_000,
                    direction="out",
                    payee="Swiggy",
                    narration="UPI/SWIGGY",
                    external_key="sbi:001",
                ),
            ),
        )

        assert [row.id for row in await recon.list_statements_by_account(conn, account_id)] == [
            statement_id
        ]
        workspace = await recon.get_statement_workspace(conn, statement_id)
        assert workspace is not None
        assert workspace.statement.status == "open"
        assert workspace.lines[0].status == "unmatched"
        assert workspace.matches == ()

        match_id = await recon.insert_match(
            conn,
            line_id=line_ids[0],
            ledger_transaction_id=42,
            method="manual",
        )
        assert match_id > 0
        assert await recon.update_line_status(conn, line_ids[0], status="matched")
        assert await recon.set_statement_status(conn, statement_id, status="reconciled")

        workspace = await recon.get_statement_workspace(conn, statement_id)
        assert workspace is not None
        assert workspace.statement.status == "reconciled"
        assert workspace.lines[0].status == "matched"
        assert workspace.matches[0].ledger_transaction_id == 42

        assert await recon.delete_match(conn, line_ids[0])
        assert await recon.update_line_status(conn, line_ids[0], status="unmatched")
        workspace = await recon.get_statement_workspace(conn, statement_id)
        assert workspace is not None
        assert workspace.matches == ()
        assert workspace.lines[0].status == "unmatched"
