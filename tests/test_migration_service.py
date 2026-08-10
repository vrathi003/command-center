from __future__ import annotations

from datetime import date
from pathlib import Path

import aiosqlite
import pytest

from finance_common.db import ensure_database
from finance_common.migration.service import apply, dry_run
from finance_common.project_config import is_legacy_cutover
from finance_common.repositories.transactions import insert_transaction


async def _account_ids(conn: aiosqlite.Connection) -> dict[str, int]:
    await conn.executemany(
        "INSERT INTO accounts (name, type, account_class) VALUES (?, ?, ?)",
        [
            ("Migration Bank", "savings", "asset_cash"),
            ("Migration Wallet", "wallet", "asset_cash"),
        ],
    )
    await conn.commit()
    cursor = await conn.execute(
        "SELECT id, name FROM accounts WHERE name IN ('Migration Bank', 'Migration Wallet')"
    )
    return {str(name): int(account_id) for account_id, name in await cursor.fetchall()}


async def _insert_fixture_rows(conn: aiosqlite.Connection, account_ids: dict[str, int]) -> None:
    common = {
        "tx_date": date(2026, 8, 10),
        "amount_paise": 10_000,
        "category": "Food",
        "merchant": "Fixture merchant",
        "payment_mode": "upi",
        "notes": None,
        "source": "import",
    }
    await insert_transaction(
        conn,
        **common,
        account="Migration Bank",
        account_id=account_ids["Migration Bank"],
    )
    await insert_transaction(
        conn,
        **common,
        account="Migration Bank",
        account_id=account_ids["Migration Bank"],
        transaction_type="credit",
    )
    deleted_id = await insert_transaction(
        conn,
        **common,
        account="Migration Bank",
        account_id=account_ids["Migration Bank"],
    )
    await conn.execute("UPDATE transactions SET is_deleted = 1 WHERE id = ?", (deleted_id,))
    await conn.commit()
    await insert_transaction(conn, **common, account=None, account_id=None)
    await insert_transaction(
        conn,
        **common,
        account="Migration Bank",
        account_id=account_ids["Migration Bank"],
        transaction_type="transfer",
        transfer_pair_id="fixture-transfer",
    )
    await insert_transaction(
        conn,
        **common,
        account="Migration Wallet",
        account_id=account_ids["Migration Wallet"],
        transaction_type="transfer",
        transfer_pair_id="fixture-transfer",
    )


async def _table_count(conn: aiosqlite.Connection, table: str) -> int:
    cursor = await conn.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
    row = await cursor.fetchone()
    assert row is not None
    return int(row[0])


@pytest.mark.asyncio
async def test_dry_run_reports_legacy_plan_without_writing(tmp_path: Path) -> None:
    db = tmp_path / "migration.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        await _insert_fixture_rows(conn, await _account_ids(conn))

        report = await dry_run(conn)

        assert (report.migrated, report.quarantined, report.skipped_deleted, report.noop) == (
            3,
            1,
            1,
            0,
        )
        assert report.backup_path is None
        assert report.cutover_at is None
        assert await _table_count(conn, "ledger_transactions") == 0
        assert await _table_count(conn, "intake_candidates") == 0
        assert await is_legacy_cutover(conn) is False
        legacy_table = await (
            await conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name = 'legacy_transactions'"
            )
        ).fetchone()
        assert legacy_table is None


@pytest.mark.asyncio
async def test_apply_posts_history_archives_backup_and_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "migration.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        account_ids = await _account_ids(conn)
        await _insert_fixture_rows(conn, account_ids)

        report = await apply(conn, db_path=db)

        assert (report.migrated, report.quarantined, report.skipped_deleted, report.noop) == (
            3,
            1,
            1,
            0,
        )
        assert report.backup_path is not None
        assert Path(report.backup_path).is_file()
        assert report.cutover_at is not None
        assert await _table_count(conn, "ledger_transactions") == 3
        assert await _table_count(conn, "legacy_transactions") == 6
        assert await is_legacy_cutover(conn) is True

        opening_balance_candidates = await (
            await conn.execute(
                """
                SELECT suggested_account_id
                FROM intake_candidates
                WHERE quarantine_reason = 'needs_opening_balance'
                ORDER BY suggested_account_id
                """
            )
        ).fetchall()
        assert [int(row[0]) for row in opening_balance_candidates] == sorted(account_ids.values())

        second_report = await apply(conn, db_path=db)

    assert second_report.backup_path != report.backup_path
    assert (second_report.migrated, second_report.quarantined, second_report.skipped_deleted) == (
        0,
        0,
        1,
    )
    assert second_report.noop == 4


@pytest.mark.asyncio
async def test_apply_populates_an_existing_empty_legacy_archive(tmp_path: Path) -> None:
    db = tmp_path / "migration.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        account_ids = await _account_ids(conn)
        await _insert_fixture_rows(conn, account_ids)
        await conn.execute("CREATE TABLE legacy_transactions AS SELECT * FROM transactions WHERE 0")
        await conn.commit()

        await apply(conn, db_path=db)

        assert await _table_count(conn, "legacy_transactions") == 6
