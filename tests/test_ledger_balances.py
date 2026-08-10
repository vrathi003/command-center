from __future__ import annotations

from datetime import date
from pathlib import Path

import aiosqlite
import pytest

from finance_common.db import ensure_database
from finance_common.ledger import builders
from finance_common.ledger import service as ledger_service
from finance_common.ledger.balances import (
    account_balance_paise,
    balances_for_accounts,
    net_worth_totals,
)
from finance_common.ledger.models import NewPosting, PostTransactionInput


async def _account_ids(conn: aiosqlite.Connection) -> dict[str, int]:
    accounts = (
        ("Bank", "savings", "asset_cash"),
        ("Credit Card", "credit_card", "liability_cc"),
        ("Investment", "investment", "asset_investment"),
        ("Expenses", "expense", "expense"),
    )
    await conn.executemany(
        "INSERT INTO accounts (name, type, account_class) VALUES (?, ?, ?)",
        accounts,
    )
    await conn.commit()
    cursor = await conn.execute(
        """
        SELECT id, name
        FROM accounts
        WHERE name IN ('Bank', 'Credit Card', 'Investment', 'Expenses')
        """
    )
    return {str(name): int(account_id) for account_id, name in await cursor.fetchall()}


async def _post(
    conn: aiosqlite.Connection,
    postings: tuple[NewPosting, ...],
) -> int:
    return await ledger_service.post(
        conn,
        PostTransactionInput(tx_date=date(2026, 8, 1), postings=postings),
    )


@pytest.mark.asyncio
async def test_balances_and_net_worth_use_only_posted_transaction_postings(
    tmp_path: Path,
) -> None:
    db = tmp_path / "ledger.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)
        await _post(
            conn,
            builders.build_bank_expense(
                bank_id=ids["Bank"],
                expense_account_id=ids["Expenses"],
                amount_paise=10_000,
                category="Food",
            ),
        )
        await _post(
            conn,
            builders.build_cc_swipe(
                cc_id=ids["Credit Card"],
                expense_account_id=ids["Expenses"],
                amount_paise=20_000,
                category="Shopping",
            ),
        )
        await _post(
            conn,
            builders.build_cc_bill_pay(
                bank_id=ids["Bank"],
                cc_id=ids["Credit Card"],
                amount_paise=5_000,
            ),
        )
        await _post(
            conn,
            builders.build_investment_buy(
                bank_id=ids["Bank"],
                investment_account_id=ids["Investment"],
                amount_paise=30_000,
            ),
        )
        void_id = await _post(
            conn,
            builders.build_bank_expense(
                bank_id=ids["Bank"],
                expense_account_id=ids["Expenses"],
                amount_paise=1_000,
                category="Ignored",
            ),
        )
        await ledger_service.void(conn, void_id)

        assert await account_balance_paise(conn, ids["Bank"]) == -45_000
        assert await balances_for_accounts(conn, [ids["Credit Card"], ids["Investment"]]) == {
            ids["Credit Card"]: -15_000,
            ids["Investment"]: 30_000,
        }
        assert await net_worth_totals(conn) == (-15_000, 15_000, -30_000)
