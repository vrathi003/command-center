from __future__ import annotations

from datetime import date
from pathlib import Path

import aiosqlite
import pytest

from finance_common.db import ensure_database
from finance_common.ledger import builders
from finance_common.ledger import service as ledger_service
from finance_common.ledger.errors import LedgerError, UnbalancedTransactionError
from finance_common.ledger.models import NewPosting, PostTransactionInput


async def _account_ids(conn: aiosqlite.Connection) -> dict[str, int]:
    await conn.execute(
        "INSERT INTO accounts (name, type, account_class) VALUES ('A', 'savings', 'asset_cash')"
    )
    await conn.execute(
        "INSERT INTO accounts (name, type, account_class) VALUES ('E', 'expense', 'expense')"
    )
    await conn.commit()
    cur = await conn.execute("SELECT id, name FROM accounts WHERE name IN ('A', 'E')")
    return {name: account_id for account_id, name in await cur.fetchall()}


@pytest.mark.asyncio
async def test_reject_unbalanced(tmp_path: Path) -> None:
    db = tmp_path / "l.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)
        with pytest.raises(UnbalancedTransactionError):
            await ledger_service.post(
                conn,
                PostTransactionInput(
                    tx_date=date(2026, 8, 1),
                    postings=(
                        NewPosting(ids["E"], 10_000, "Food Delivery"),
                        NewPosting(ids["A"], -9_000),
                    ),
                ),
            )


@pytest.mark.asyncio
async def test_post_balanced_expense(tmp_path: Path) -> None:
    db = tmp_path / "l.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)
        tx_id = await ledger_service.post(
            conn,
            PostTransactionInput(
                tx_date=date(2026, 8, 1),
                postings=(
                    NewPosting(ids["E"], 50_000, "Food Delivery"),
                    NewPosting(ids["A"], -50_000),
                ),
                source="manual",
                payee="Swiggy",
            ),
        )
        posted = await ledger_service.get_transaction(conn, tx_id)
        assert posted.status == "posted"
        assert sum(posting.amount_paise for posting in posted.postings) == 0


@pytest.mark.asyncio
async def test_post_rejects_expense_posting_without_category(tmp_path: Path) -> None:
    db = tmp_path / "l.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)
        with pytest.raises(LedgerError, match="category"):
            await ledger_service.post(
                conn,
                PostTransactionInput(
                    tx_date=date(2026, 8, 1),
                    postings=(
                        NewPosting(ids["E"], 50_000),
                        NewPosting(ids["A"], -50_000),
                    ),
                ),
            )


@pytest.mark.asyncio
async def test_post_rejects_zero_amount_in_otherwise_balanced_postings(
    tmp_path: Path,
) -> None:
    db = tmp_path / "l.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)
        with pytest.raises(LedgerError):
            await ledger_service.post(
                conn,
                PostTransactionInput(
                    tx_date=date(2026, 8, 1),
                    postings=(
                        NewPosting(ids["E"], 10_000, "Food Delivery"),
                        NewPosting(ids["A"], 0),
                        NewPosting(ids["A"], -10_000),
                    ),
                ),
            )


@pytest.mark.asyncio
async def test_post_rejects_missing_account_id(tmp_path: Path) -> None:
    db = tmp_path / "l.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)
        with pytest.raises(LedgerError, match="Unknown account ids"):
            await ledger_service.post(
                conn,
                PostTransactionInput(
                    tx_date=date(2026, 8, 1),
                    postings=(
                        NewPosting(None, 500),  # type: ignore[arg-type]
                        NewPosting(ids["A"], -500),
                    ),
                ),
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("amount", [500.0, True])
async def test_post_rejects_non_integer_amount_paise(tmp_path: Path, amount: float | bool) -> None:
    db = tmp_path / "l.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)
        with pytest.raises(LedgerError, match="integer paise"):
            await ledger_service.post(
                conn,
                PostTransactionInput(
                    tx_date=date(2026, 8, 1),
                    postings=(
                        NewPosting(ids["E"], amount),  # type: ignore[arg-type]
                        NewPosting(ids["A"], -amount),  # type: ignore[arg-type,operator]
                    ),
                ),
            )


@pytest.mark.asyncio
async def test_post_returns_existing_id_for_malformed_idempotent_retry(
    tmp_path: Path,
) -> None:
    db = tmp_path / "l.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)
        inp = PostTransactionInput(
            tx_date=date(2026, 8, 1),
            postings=(NewPosting(ids["E"], 500, "Other"), NewPosting(ids["A"], -500)),
            external_key="import:row:1",
        )
        first_id = await ledger_service.post(conn, inp)
        second_id = await ledger_service.post(
            conn,
            PostTransactionInput(
                tx_date=date(2026, 8, 2),
                postings=(NewPosting(ids["E"], 500), NewPosting(ids["A"], -400)),
                external_key="import:row:1",
            ),
        )
        assert second_id == first_id


@pytest.mark.asyncio
async def test_void_marks_header_and_rejects_double_void(tmp_path: Path) -> None:
    db = tmp_path / "l.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)
        tx_id = await ledger_service.post(
            conn,
            PostTransactionInput(
                tx_date=date(2026, 8, 1),
                postings=(NewPosting(ids["E"], 500, "Other"), NewPosting(ids["A"], -500)),
            ),
        )
        await ledger_service.void(conn, tx_id)
        assert (await ledger_service.get_transaction(conn, tx_id)).status == "void"
        with pytest.raises(LedgerError):
            await ledger_service.void(conn, tx_id)


def _assert_balanced(postings: tuple[NewPosting, ...]) -> None:
    assert len(postings) >= 2
    assert sum(p.amount_paise for p in postings) == 0
    assert all(p.amount_paise != 0 for p in postings)


def test_build_bank_expense() -> None:
    postings = builders.build_bank_expense(
        bank_id=1,
        expense_account_id=2,
        amount_paise=10_000,
        category="Food Delivery",
    )
    assert postings == (
        NewPosting(2, 10_000, "Food Delivery"),
        NewPosting(1, -10_000),
    )
    _assert_balanced(postings)


def test_build_bank_income() -> None:
    postings = builders.build_bank_income(
        bank_id=1,
        income_account_id=3,
        amount_paise=50_000,
        category="Salary",
    )
    assert postings == (
        NewPosting(1, 50_000),
        NewPosting(3, -50_000, "Salary"),
    )
    _assert_balanced(postings)


def test_build_transfer() -> None:
    postings = builders.build_transfer(
        from_account_id=1,
        to_account_id=4,
        amount_paise=25_000,
    )
    assert postings == (
        NewPosting(4, 25_000),
        NewPosting(1, -25_000),
    )
    _assert_balanced(postings)


def test_build_cc_swipe() -> None:
    postings = builders.build_cc_swipe(
        cc_id=5,
        expense_account_id=2,
        amount_paise=10_000,
        category="Shopping",
    )
    assert postings == (
        NewPosting(2, 10_000, "Shopping"),
        NewPosting(5, -10_000),
    )
    _assert_balanced(postings)


def test_build_cc_bill_pay() -> None:
    postings = builders.build_cc_bill_pay(
        bank_id=1,
        cc_id=5,
        amount_paise=10_000,
    )
    assert postings == (
        NewPosting(5, 10_000),
        NewPosting(1, -10_000),
    )
    _assert_balanced(postings)


def test_build_investment_buy() -> None:
    postings = builders.build_investment_buy(
        bank_id=1,
        investment_account_id=6,
        amount_paise=100_000,
    )
    assert postings == (
        NewPosting(6, 100_000),
        NewPosting(1, -100_000),
    )
    _assert_balanced(postings)
