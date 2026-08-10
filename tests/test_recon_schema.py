from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from finance_common.db import ensure_database, schema_sql
from finance_common.db.migrations import apply_migrations


@pytest.mark.asyncio
async def test_recon_tables_exist_with_required_columns_after_ensure(tmp_path: Path) -> None:
    db = tmp_path / "recon.db"
    await ensure_database(db)

    expected_columns = {
        "recon_statements": {
            "id",
            "account_id",
            "period_start",
            "period_end",
            "opening_balance_paise",
            "closing_balance_paise",
            "status",
            "source",
            "filename",
            "created_at",
            "updated_at",
        },
        "recon_statement_lines": {
            "id",
            "statement_id",
            "tx_date",
            "amount_paise",
            "direction",
            "payee",
            "narration",
            "external_key",
            "status",
            "ignore_reason",
        },
        "recon_matches": {
            "id",
            "line_id",
            "ledger_transaction_id",
            "method",
            "confirmed_at",
        },
    }

    async with aiosqlite.connect(db) as conn:
        for table, expected in expected_columns.items():
            rows = await (await conn.execute(f"PRAGMA table_info({table})")).fetchall()
            assert expected <= {str(row[1]) for row in rows}


@pytest.mark.asyncio
async def test_migrations_add_recon_tables_to_pre_recon_database(tmp_path: Path) -> None:
    db = tmp_path / "old.db"
    async with aiosqlite.connect(db) as conn:
        await conn.executescript(schema_sql())
        await conn.executescript(
            """
            DROP TABLE recon_matches;
            DROP TABLE recon_statement_lines;
            DROP TABLE recon_statements;
            """
        )

        await apply_migrations(conn)

        rows = await (
            await conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name IN ('recon_statements', 'recon_statement_lines', 'recon_matches')"
            )
        ).fetchall()

    assert {str(row[0]) for row in rows} == {
        "recon_statements",
        "recon_statement_lines",
        "recon_matches",
    }
