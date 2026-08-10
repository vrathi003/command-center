from __future__ import annotations

from dataclasses import asdict
from datetime import date
from pathlib import Path

import aiosqlite
import pytest

from finance_common.db import ensure_database
from finance_common.ledger.models import NewPosting
from finance_common.migration.plan_row import plan_legacy_row
from finance_common.migration.resolve import resolve_account_id
from finance_common.repositories.transactions import TransactionRow


async def _account_ids(conn: aiosqlite.Connection) -> dict[str, int]:
    accounts = (
        ("SBI Personal", "savings", "asset_cash"),
        ("Wallet", "wallet", "asset_cash"),
        ("Groceries", "expense", "expense"),
    )
    await conn.executemany(
        "INSERT INTO accounts (name, type, account_class) VALUES (?, ?, ?)",
        accounts,
    )
    await conn.commit()
    cursor = await conn.execute(
        "SELECT id, name FROM accounts WHERE name IN ('SBI Personal', 'Wallet', 'Groceries', "
        "'Uncategorized Expense', 'Uncategorized Income')"
    )
    return {str(name): int(account_id) for account_id, name in await cursor.fetchall()}


def _row(
    *,
    tx_id: int = 1,
    account_id: int | None = None,
    account: str | None = "SBI Personal",
    transaction_type: str = "debit",
    transfer_pair_id: str | None = None,
) -> TransactionRow:
    return TransactionRow(
        id=tx_id,
        date="2026-08-10",
        amount_paise=12_345,
        category="Food",
        merchant="Example payee",
        payment_mode="upi",
        account=account,
        notes="Example note",
        transaction_type=transaction_type,
        source="import",
        discord_message_id=None,
        account_id=account_id,
        transfer_pair_id=transfer_pair_id,
        tags=None,
    )


@pytest.mark.asyncio
async def test_resolve_account_id_prefers_id_then_exact_and_unique_casefold_name(
    tmp_path: Path,
) -> None:
    db = tmp_path / "migration.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)

        assert await resolve_account_id(
            conn, account_id=ids["SBI Personal"], account_name="not-used"
        ) == ids["SBI Personal"]
        assert await resolve_account_id(conn, account_id=None, account_name="SBI Personal") == ids[
            "SBI Personal"
        ]
        assert await resolve_account_id(conn, account_id=None, account_name="sbi personal") == ids[
            "SBI Personal"
        ]


@pytest.mark.asyncio
async def test_plan_legacy_debit_resolves_sbi_personal_name_and_plans_postings(
    tmp_path: Path,
) -> None:
    db = tmp_path / "migration.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)
        planned = await plan_legacy_row(conn, _row(account_id=None), already_posted=set())

    assert planned.kind == "post"
    assert planned.external_key == "legacy:txn:1"
    assert planned.legacy_ids == (1,)
    assert planned.post_input is not None
    assert planned.post_input.tx_date == date(2026, 8, 10)
    assert planned.post_input.postings == (
        NewPosting(ids["Uncategorized Expense"], 12_345, "Food"),
        NewPosting(ids["SBI Personal"], -12_345),
    )


@pytest.mark.asyncio
async def test_plan_legacy_credit_plans_income_postings(tmp_path: Path) -> None:
    db = tmp_path / "migration.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)
        planned = await plan_legacy_row(
            conn,
            _row(account_id=ids["SBI Personal"], transaction_type="credit"),
            already_posted=set(),
        )

    assert planned.kind == "post"
    assert planned.post_input is not None
    assert planned.post_input.postings == (
        NewPosting(ids["SBI Personal"], 12_345),
        NewPosting(ids["Uncategorized Income"], -12_345, "Food"),
    )


@pytest.mark.asyncio
async def test_plan_legacy_transfer_with_sibling_plans_one_transfer(tmp_path: Path) -> None:
    db = tmp_path / "migration.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)
        planned = await plan_legacy_row(
            conn,
            _row(
                tx_id=10,
                account_id=ids["SBI Personal"],
                transaction_type="transfer",
                transfer_pair_id="pair-1",
            ),
            paired_sibling=_row(
                tx_id=11,
                account_id=ids["Wallet"],
                account="Wallet",
                transaction_type="transfer",
                transfer_pair_id="pair-1",
            ),
            already_posted=set(),
        )

    assert planned.kind == "post"
    assert planned.external_key == "legacy:pair:pair-1"
    assert planned.legacy_ids == (10, 11)
    assert planned.post_input is not None
    assert planned.post_input.postings == (
        NewPosting(ids["Wallet"], 12_345),
        NewPosting(ids["SBI Personal"], -12_345),
    )


@pytest.mark.asyncio
async def test_plan_legacy_row_quarantines_missing_account_and_orphan_transfer(
    tmp_path: Path,
) -> None:
    db = tmp_path / "migration.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        missing = await plan_legacy_row(
            conn, _row(account_id=None, account=None), already_posted=set()
        )
        orphan = await plan_legacy_row(
            conn,
            _row(
                transaction_type="transfer",
                transfer_pair_id="orphan-pair",
            ),
            already_posted=set(),
        )

    assert missing.kind == "quarantine"
    assert missing.quarantine_reason == "legacy_migration:missing_account"
    assert orphan.kind == "quarantine"
    assert orphan.quarantine_reason == "legacy_migration:orphan_transfer"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("sibling_transaction_type", "sibling_pair_id", "sibling_deleted"),
    [
        ("debit", "pair-1", 0),
        ("transfer", "different-pair", 0),
        ("transfer", "pair-1", 1),
    ],
)
async def test_plan_legacy_transfer_quarantines_invalid_sibling(
    tmp_path: Path,
    sibling_transaction_type: str,
    sibling_pair_id: str,
    sibling_deleted: int,
) -> None:
    db = tmp_path / "migration.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)
        planned = await plan_legacy_row(
            conn,
            _row(
                tx_id=10,
                account_id=ids["SBI Personal"],
                transaction_type="transfer",
                transfer_pair_id="pair-1",
            ),
            paired_sibling={
                **asdict(
                    _row(
                        tx_id=11,
                        account_id=ids["Wallet"],
                        account="Wallet",
                        transaction_type=sibling_transaction_type,
                        transfer_pair_id=sibling_pair_id,
                    )
                ),
                "is_deleted": sibling_deleted,
            },
            already_posted=set(),
        )

    assert planned.kind == "quarantine"
    assert planned.quarantine_reason == "legacy_migration:invalid_transfer"
    assert planned.legacy_ids == (10, 11)


@pytest.mark.asyncio
async def test_plan_legacy_row_skips_deleted_and_noops_posted_key(tmp_path: Path) -> None:
    db = tmp_path / "migration.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)
        deleted = await plan_legacy_row(
            conn,
            {**asdict(_row(account_id=ids["SBI Personal"])), "is_deleted": 1},
            already_posted=set(),
        )
        noop = await plan_legacy_row(
            conn,
            _row(account_id=ids["SBI Personal"]),
            already_posted={"legacy:txn:1"},
        )

    assert deleted.kind == "skip_deleted"
    assert noop.kind == "noop"


@pytest.mark.asyncio
@pytest.mark.parametrize("is_deleted", [0, "0", False, None])
async def test_plan_legacy_row_treats_falsey_deleted_values_as_active(
    tmp_path: Path, is_deleted: object
) -> None:
    db = tmp_path / "migration.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)
        planned = await plan_legacy_row(
            conn,
            {**asdict(_row(account_id=ids["SBI Personal"])), "is_deleted": is_deleted},
            already_posted=set(),
        )

    assert planned.kind == "post"


@pytest.mark.asyncio
@pytest.mark.parametrize("is_deleted", [1, "1", True])
async def test_plan_legacy_row_skips_true_deleted_values(tmp_path: Path, is_deleted: object) -> None:
    db = tmp_path / "migration.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)
        planned = await plan_legacy_row(
            conn,
            {**asdict(_row(account_id=ids["SBI Personal"])), "is_deleted": is_deleted},
            already_posted=set(),
        )

    assert planned.kind == "skip_deleted"
