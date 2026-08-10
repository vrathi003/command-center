from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from finance_common.db import ensure_database, schema_sql
from finance_common.db.migrations import apply_migrations
from finance_common.types import AccountClass


@pytest.mark.asyncio
async def test_ledger_tables_exist_after_ensure(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        cur = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('ledger_transactions', 'ledger_postings')"
        )
        names = {r[0] for r in await cur.fetchall()}
        assert names == {"ledger_transactions", "ledger_postings"}
        cur = await conn.execute("PRAGMA table_info(accounts)")
        cols = {r[1] for r in await cur.fetchall()}
        assert "account_class" in cols
        cur = await conn.execute(
            "SELECT name FROM accounts WHERE account_class = ?",
            (AccountClass.EQUITY.value,),
        )
        equity_names = {r[0] for r in await cur.fetchall()}
        assert "Opening Balance Equity" in equity_names


@pytest.mark.asyncio
async def test_migrations_add_ledger_tables_to_pre_ledger_database(tmp_path: Path) -> None:
    db = tmp_path / "old.db"
    async with aiosqlite.connect(db) as conn:
        await conn.executescript(schema_sql())
        await conn.executescript(
            """
            DROP TABLE ledger_postings;
            DROP TABLE ledger_transactions;
            DROP TABLE accounts;
            CREATE TABLE accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                institution TEXT,
                currency TEXT NOT NULL DEFAULT 'INR',
                is_active INTEGER NOT NULL DEFAULT 1
            );
            """
        )
        await apply_migrations(conn)

        tables = {
            str(row[0])
            for row in await (
                await conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' "
                    "AND name IN ('ledger_transactions', 'ledger_postings')"
                )
            ).fetchall()
        }
        account_columns = {
            str(row[1])
            for row in await (await conn.execute("PRAGMA table_info(accounts)")).fetchall()
        }
        posting_columns = {
            str(row[1])
            for row in await (await conn.execute("PRAGMA table_info(ledger_postings)")).fetchall()
        }

        assert tables == {"ledger_transactions", "ledger_postings"}
        assert "account_class" in account_columns
        assert {"transaction_id", "account_id", "amount_paise", "category"} <= posting_columns
