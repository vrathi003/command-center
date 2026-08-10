from __future__ import annotations

from datetime import date
from pathlib import Path

import aiosqlite
import pytest

from finance_common.db import ensure_database
from finance_common.ledger import builders
from finance_common.ledger import service as ledger_service
from finance_common.ledger.models import NewPosting, PostTransactionInput


async def _account_ids(conn: aiosqlite.Connection) -> dict[str, int]:
    accounts = (
        ("Bank", "savings", "asset_cash"),
        ("Credit Card", "credit_card", "liability_cc"),
        ("Investment", "investment", "asset_investment"),
        ("Food", "expense", "expense"),
        ("Salary", "income", "income"),
    )
    await conn.executemany(
        "INSERT INTO accounts (name, type, account_class) VALUES (?, ?, ?)",
        accounts,
    )
    await conn.commit()
    cursor = await conn.execute("SELECT id, name FROM accounts")
    return {str(name): int(account_id) for account_id, name in await cursor.fetchall()}


async def _post(
    conn: aiosqlite.Connection,
    *,
    tx_date: date,
    postings: tuple[NewPosting, ...],
) -> None:
    await ledger_service.post(
        conn,
        PostTransactionInput(tx_date=tx_date, postings=postings),
    )


@pytest.mark.asyncio
async def test_budget_spend_and_cash_flow_match_golden_fixture(tmp_path: Path) -> None:
    from finance_common.ledger.reports import (
        budget_spend_by_category,
        budget_spend_total,
        cash_flow_for_accounts,
    )

    db = tmp_path / "ledger.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)
        report_date = date(2026, 8, 1)

        await _post(
            conn,
            tx_date=report_date,
            postings=builders.build_cc_swipe(
                cc_id=ids["Credit Card"],
                expense_account_id=ids["Food"],
                amount_paise=50_000,
                category="Food",
            ),
        )
        await _post(
            conn,
            tx_date=report_date,
            postings=builders.build_bank_expense(
                bank_id=ids["Bank"],
                expense_account_id=ids["Food"],
                amount_paise=20_000,
                category="Food",
            ),
        )
        await _post(
            conn,
            tx_date=report_date,
            postings=builders.build_bank_income(
                bank_id=ids["Bank"],
                income_account_id=ids["Salary"],
                amount_paise=10_000_000,
                category="Salary",
            ),
        )
        await _post(
            conn,
            tx_date=report_date,
            postings=builders.build_cc_bill_pay(
                bank_id=ids["Bank"],
                cc_id=ids["Credit Card"],
                amount_paise=50_000,
            ),
        )
        await _post(
            conn,
            tx_date=report_date,
            postings=builders.build_investment_buy(
                bank_id=ids["Bank"],
                investment_account_id=ids["Investment"],
                amount_paise=100_000,
            ),
        )

        assert await budget_spend_by_category(
            conn, start=report_date, end=report_date
        ) == {"Food": 70_000}
        assert await budget_spend_total(conn, start=report_date, end=report_date) == 70_000
        assert await cash_flow_for_accounts(
            conn,
            account_ids=[ids["Bank"]],
            start=report_date,
            end=report_date,
        ) == (10_000_000, 170_000)


@pytest.mark.asyncio
async def test_report_lenses_exclude_voided_and_out_of_range_transactions(
    tmp_path: Path,
) -> None:
    from finance_common.ledger.reports import (
        budget_spend_by_category,
        cash_flow_for_accounts,
    )

    db = tmp_path / "ledger.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)
        report_date = date(2026, 8, 1)

        void_id = await ledger_service.post(
            conn,
            PostTransactionInput(
                tx_date=report_date,
                postings=builders.build_bank_expense(
                    bank_id=ids["Bank"],
                    expense_account_id=ids["Food"],
                    amount_paise=10_000,
                    category="Food",
                ),
            ),
        )
        await ledger_service.void(conn, void_id)
        await _post(
            conn,
            tx_date=date(2026, 7, 31),
            postings=builders.build_bank_expense(
                bank_id=ids["Bank"],
                expense_account_id=ids["Food"],
                amount_paise=20_000,
                category="Food",
            ),
        )

        assert await budget_spend_by_category(
            conn, start=report_date, end=report_date
        ) == {}
        assert await cash_flow_for_accounts(
            conn,
            account_ids=[ids["Bank"]],
            start=report_date,
            end=report_date,
        ) == (0, 0)
