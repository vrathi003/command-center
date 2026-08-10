from __future__ import annotations

import asyncio
from pathlib import Path

import aiosqlite
import pytest

from finance_common.db import ensure_database
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
