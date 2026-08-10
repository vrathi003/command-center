from __future__ import annotations

from datetime import date
from pathlib import Path

import aiosqlite
import pytest

from finance_common.db import ensure_database
from finance_common.ledger import builders
from finance_common.ledger import service as ledger_service
from finance_common.ledger.models import PostTransactionInput
from finance_common.recon.models import NewStatement, NewStatementLine
from finance_common.recon.service import ReconciliationError, ReconciliationService


async def _account_ids(conn: aiosqlite.Connection) -> dict[str, int]:
    await conn.executemany(
        "INSERT INTO accounts (name, type, account_class) VALUES (?, ?, ?)",
        (
            ("Bank", "savings", "asset_cash"),
            ("Expense", "expense", "expense"),
        ),
    )
    await conn.commit()
    cursor = await conn.execute("SELECT id, name FROM accounts")
    return {str(name): int(account_id) for account_id, name in await cursor.fetchall()}


@pytest.mark.asyncio
async def test_soft_close_requires_cleared_lines_and_matching_as_of_balance(
    tmp_path: Path,
) -> None:
    db = tmp_path / "recon-service.db"
    await ensure_database(db)

    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)
        service = ReconciliationService(conn)
        statement_id = await service.import_rows(
            NewStatement(
                account_id=ids["Bank"],
                period_start=date(2026, 8, 1),
                period_end=date(2026, 8, 31),
                opening_balance_paise=0,
                closing_balance_paise=-10_000,
                source="upload",
            ),
            (
                NewStatementLine(
                    tx_date=date(2026, 8, 10),
                    amount_paise=10_000,
                    direction="out",
                    payee="Coffee",
                ),
            ),
        )

        with pytest.raises(ReconciliationError, match="unmatched"):
            await service.soft_close(statement_id)

        tx_id = await ledger_service.post(
            conn,
            PostTransactionInput(
                tx_date=date(2026, 8, 10),
                postings=builders.build_bank_expense(
                    bank_id=ids["Bank"],
                    expense_account_id=ids["Expense"],
                    amount_paise=10_000,
                    category="Food",
                ),
            ),
        )
        await service.confirm_match(statement_id, 1, tx_id)
        await ledger_service.post(
            conn,
            PostTransactionInput(
                tx_date=date(2026, 9, 1),
                postings=builders.build_bank_expense(
                    bank_id=ids["Bank"],
                    expense_account_id=ids["Expense"],
                    amount_paise=5_000,
                    category="Food",
                ),
            ),
        )

        status = await service.soft_close(statement_id)
        assert status.is_balanced
        assert status.unmatched_line_count == 0

        await service.reopen(statement_id)
        await service.unmatch(statement_id, 1)
        with pytest.raises(ReconciliationError, match="unmatched"):
            await service.soft_close(statement_id)


@pytest.mark.asyncio
async def test_soft_close_rejects_a_cleared_statement_when_balances_differ(
    tmp_path: Path,
) -> None:
    db = tmp_path / "recon-service.db"
    await ensure_database(db)

    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)
        service = ReconciliationService(conn)
        statement_id = await service.import_rows(
            NewStatement(
                account_id=ids["Bank"],
                period_start=date(2026, 8, 1),
                period_end=date(2026, 8, 31),
                opening_balance_paise=0,
                closing_balance_paise=-10_000,
                source="upload",
            ),
            (
                NewStatementLine(
                    tx_date=date(2026, 8, 10),
                    amount_paise=10_000,
                    direction="out",
                ),
            ),
        )
        await service.ignore_line(statement_id, 1, "duplicate statement row")

        with pytest.raises(ReconciliationError, match="balance"):
            await service.soft_close(statement_id)
