from __future__ import annotations

from datetime import date
from pathlib import Path

import aiosqlite
import pytest

from finance_common.db import ensure_database
from finance_common.intake.models import Candidate
from finance_common.intake.posting_plan import IntakePlanError, plan_postings, plan_transfer
from finance_common.ledger.models import NewPosting


async def _account_ids(conn: aiosqlite.Connection) -> dict[str, int]:
    accounts = (
        ("Primary Bank", "savings", "asset_cash"),
        ("Wallet", "wallet", "asset_cash"),
        ("Credit Card", "credit_card", "liability_cc"),
        ("Groceries", "expense", "expense"),
    )
    await conn.executemany(
        "INSERT INTO accounts (name, type, account_class) VALUES (?, ?, ?)",
        accounts,
    )
    await conn.commit()
    cursor = await conn.execute(
        "SELECT id, name FROM accounts "
        "WHERE name IN ('Primary Bank', 'Wallet', 'Credit Card', 'Groceries', "
        "'Uncategorized Expense', 'Uncategorized Income')"
    )
    return {str(name): int(account_id) for account_id, name in await cursor.fetchall()}


def _candidate(
    *,
    account_id: int | None,
    direction: str = "out",
    category: str | None = None,
    counter_account_id: int | None = None,
) -> Candidate:
    return Candidate(
        source="import",
        tx_date=date(2026, 8, 10),
        amount_paise=12_345,
        direction=direction,  # type: ignore[arg-type]
        suggested_account_id=account_id,
        payee="Example payee",
        narration="Example narration",
        suggested_category=category,
        suggested_counter_account_id=counter_account_id,
        external_key="import:example:1",
    )


@pytest.mark.asyncio
async def test_plan_postings_builds_bank_expense_with_suggested_counter_account(
    tmp_path: Path,
) -> None:
    db = tmp_path / "intake.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)

        plan = await plan_postings(
            conn,
            _candidate(
                account_id=ids["Primary Bank"],
                category="Food",
                counter_account_id=ids["Groceries"],
            ),
        )

    assert plan.tx_date == date(2026, 8, 10)
    assert plan.payee == "Example payee"
    assert plan.notes == "Example narration"
    assert plan.source == "import"
    assert plan.external_key == "import:example:1"
    assert plan.postings == (
        NewPosting(ids["Groceries"], 12_345, "Food"),
        NewPosting(ids["Primary Bank"], -12_345),
    )


@pytest.mark.asyncio
async def test_plan_postings_builds_bank_income_with_system_account_and_other_category(
    tmp_path: Path,
) -> None:
    db = tmp_path / "intake.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)

        plan = await plan_postings(conn, _candidate(account_id=ids["Wallet"], direction="in"))

    assert plan.postings == (
        NewPosting(ids["Wallet"], 12_345),
        NewPosting(ids["Uncategorized Income"], -12_345, "Other"),
    )


@pytest.mark.asyncio
async def test_plan_postings_builds_credit_card_swipe_with_system_expense_account(
    tmp_path: Path,
) -> None:
    db = tmp_path / "intake.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)

        plan = await plan_postings(
            conn,
            _candidate(account_id=ids["Credit Card"], category="Shopping"),
        )

    assert plan.postings == (
        NewPosting(ids["Uncategorized Expense"], 12_345, "Shopping"),
        NewPosting(ids["Credit Card"], -12_345),
    )


@pytest.mark.asyncio
async def test_plan_postings_rejects_credit_card_income_without_bank_account(
    tmp_path: Path,
) -> None:
    db = tmp_path / "intake.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)

        with pytest.raises(IntakePlanError, match="bank"):
            await plan_postings(conn, _candidate(account_id=ids["Credit Card"], direction="in"))


@pytest.mark.asyncio
async def test_plan_postings_rejects_missing_suggested_account(tmp_path: Path) -> None:
    db = tmp_path / "intake.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        await _account_ids(conn)

        with pytest.raises(IntakePlanError, match="account"):
            await plan_postings(conn, _candidate(account_id=None))


@pytest.mark.asyncio
async def test_plan_transfer_builds_transfer_and_preserves_candidate_metadata(
    tmp_path: Path,
) -> None:
    db = tmp_path / "intake.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)

        plan = await plan_transfer(
            conn,
            from_account_id=ids["Primary Bank"],
            to_account_id=ids["Wallet"],
            amount_paise=50_000,
            tx_date=date(2026, 8, 11),
            source="manual",
            payee="Wallet top-up",
            notes="Move funds",
            external_key="manual:transfer:1",
        )

    assert plan.tx_date == date(2026, 8, 11)
    assert plan.payee == "Wallet top-up"
    assert plan.notes == "Move funds"
    assert plan.source == "manual"
    assert plan.external_key == "manual:transfer:1"
    assert plan.postings == (
        NewPosting(ids["Wallet"], 50_000),
        NewPosting(ids["Primary Bank"], -50_000),
    )
