from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from finance_common.db import ensure_database
from finance_common.ledger.errors import LedgerIntegrityError
from finance_common.ledger.integrity import assert_ledger_healthy


@pytest.mark.asyncio
async def test_assert_ledger_healthy_rejects_unbalanced_posted_transaction(
    tmp_path: Path,
) -> None:
    db = tmp_path / "ledger.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        await conn.execute(
            "INSERT INTO accounts (name, type, account_class) VALUES (?, ?, ?)",
            ("Cash", "savings", "asset_cash"),
        )
        header = await conn.execute(
            "INSERT INTO ledger_transactions (date, source) VALUES (?, ?)",
            ("2026-08-10", "test"),
        )
        transaction_id = header.lastrowid
        assert transaction_id is not None
        await conn.execute(
            """
            INSERT INTO ledger_postings (transaction_id, account_id, amount_paise)
            VALUES (?, ?, ?)
            """,
            (transaction_id, 1, 100),
        )
        await conn.commit()

        with pytest.raises(LedgerIntegrityError, match=str(transaction_id)):
            await assert_ledger_healthy(conn)


@pytest.mark.asyncio
async def test_assert_ledger_healthy_rejects_posted_transaction_with_one_posting(
    tmp_path: Path,
) -> None:
    db = tmp_path / "ledger.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        await conn.execute(
            "INSERT INTO accounts (name, type, account_class) VALUES (?, ?, ?)",
            ("Cash", "savings", "asset_cash"),
        )
        header = await conn.execute(
            "INSERT INTO ledger_transactions (date, source) VALUES (?, ?)",
            ("2026-08-10", "test"),
        )
        transaction_id = header.lastrowid
        assert transaction_id is not None
        await conn.commit()

        with pytest.raises(LedgerIntegrityError, match=str(transaction_id)):
            await assert_ledger_healthy(conn)
