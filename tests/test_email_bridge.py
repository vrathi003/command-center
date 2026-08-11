"""Tests for email staging → intake bridge approve flows."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import aiosqlite
import pytest

from finance_common.db import ensure_database
from finance_common.intake.email_bridge import (
    ApproveOverrides,
    EmailStagingNotFoundError,
    EmailStagingStatusError,
    TransferOverrides,
    approve_as_transfer,
    approve_staged_item,
)
from finance_common.ledger import service as ledger_service
from finance_common.ledger.models import NewPosting, PostTransactionInput


async def _seed_accounts(conn: aiosqlite.Connection) -> dict[str, int]:
    await conn.executemany(
        "INSERT INTO accounts (name, type, account_class) VALUES (?, ?, ?)",
        [
            ("Bank", "savings", "asset_cash"),
            ("Bank 2", "savings", "asset_cash"),
            ("Food", "expense", "expense"),
            ("Uncategorized Expense", "expense", "expense"),
            ("Uncategorized Income", "income", "income"),
        ],
    )
    await conn.commit()
    cursor = await conn.execute("SELECT id, name FROM accounts")
    return {name: account_id for account_id, name in await cursor.fetchall()}


async def _insert_staged(
    conn: aiosqlite.Connection,
    *,
    gmail_message_id: str,
    account_id: int,
    amount_paise: int = 12_500,
    parsed_date: str = "2026-08-01",
    merchant: str = "Coffee Shop",
    tx_type: str = "debit",
    status: str = "pending",
    intake_candidate_id: int | None = None,
    raw_snippet: str | None = None,
) -> int:
    cur = await conn.execute(
        """
        INSERT INTO email_transaction_staging (
            gmail_message_id, email_date, parsed_date, parsed_amount_paise,
            parsed_merchant, parsed_category, parsed_payment_mode,
            parsed_transaction_type, suggested_account_id, status, intake_candidate_id,
            raw_snippet
        ) VALUES (?, ?, ?, ?, ?, 'Food', 'UPI', ?, ?, ?, ?, ?)
        """,
        (
            gmail_message_id,
            parsed_date,
            parsed_date,
            amount_paise,
            merchant,
            tx_type,
            account_id,
            status,
            intake_candidate_id,
            raw_snippet,
        ),
    )
    item_id = cur.lastrowid
    assert item_id is not None
    await conn.commit()
    return int(item_id)


@pytest.mark.asyncio
async def test_approve_staged_item_posts_and_links_ledger(tmp_path: Path) -> None:
    db = tmp_path / "bridge.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _seed_accounts(conn)
        item_id = await _insert_staged(
            conn, gmail_message_id="approve-post-1", account_id=ids["Bank"]
        )

        row = await approve_staged_item(
            conn,
            staging_id=item_id,
            overrides=ApproveOverrides(),
            force=False,
        )

        candidate = await (
            await conn.execute(
                "SELECT source, external_key, status FROM intake_candidates WHERE email_staging_id = ?",
                (item_id,),
            )
        ).fetchone()

    assert row.status == "approved"
    assert row.ledger_transaction_id is not None
    assert candidate is not None
    assert candidate[0] == "email"
    assert str(candidate[1]).startswith("gmail:approve-post-1")
    assert candidate[2] == "posted"


@pytest.mark.asyncio
async def test_approve_staged_item_quarantines_soft_duplicate(tmp_path: Path) -> None:
    db = tmp_path / "bridge.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _seed_accounts(conn)
        first_id = await _insert_staged(
            conn, gmail_message_id="dupe-1", account_id=ids["Bank"]
        )
        await approve_staged_item(
            conn, staging_id=first_id, overrides=ApproveOverrides(), force=False
        )
        second_id = await _insert_staged(
            conn,
            gmail_message_id="dupe-2",
            account_id=ids["Bank"],
            merchant="Coffee Shop",
        )

        row = await approve_staged_item(
            conn, staging_id=second_id, overrides=ApproveOverrides(), force=False
        )

        candidate = await (
            await conn.execute(
                "SELECT quarantine_reason FROM intake_candidates WHERE id = ?",
                (row.intake_candidate_id,),
            )
        ).fetchone()

    assert row.status == "quarantined"
    assert row.intake_candidate_id is not None
    assert candidate is not None
    assert candidate[0] == "possible_duplicate"


@pytest.mark.asyncio
async def test_approve_staged_item_force_posts_despite_duplicate(tmp_path: Path) -> None:
    db = tmp_path / "bridge.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _seed_accounts(conn)
        first_id = await _insert_staged(
            conn, gmail_message_id="force-1", account_id=ids["Bank"]
        )
        await approve_staged_item(
            conn, staging_id=first_id, overrides=ApproveOverrides(), force=False
        )
        second_id = await _insert_staged(
            conn,
            gmail_message_id="force-2",
            account_id=ids["Bank"],
            merchant="Coffee Shop",
        )

        row = await approve_staged_item(
            conn, staging_id=second_id, overrides=ApproveOverrides(), force=True
        )

    assert row.status == "approved"
    assert row.ledger_transaction_id is not None


@pytest.mark.asyncio
async def test_approve_staged_item_noop_reuses_existing_ledger_id(tmp_path: Path) -> None:
    db = tmp_path / "bridge.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _seed_accounts(conn)
        existing_tx_id = await ledger_service.post(
            conn,
            PostTransactionInput(
                tx_date=date(2026, 8, 1),
                postings=(
                    NewPosting(ids["Food"], 12_500, "Food"),
                    NewPosting(ids["Bank"], -12_500),
                ),
                external_key="gmail:noop-1",
            ),
        )
        item_id = await _insert_staged(
            conn, gmail_message_id="noop-1", account_id=ids["Bank"]
        )

        row = await approve_staged_item(
            conn, staging_id=item_id, overrides=ApproveOverrides(), force=False
        )

    assert row.status == "approved"
    assert row.ledger_transaction_id == existing_tx_id


@pytest.mark.asyncio
async def test_approve_staged_item_raises_for_missing_row(tmp_path: Path) -> None:
    db = tmp_path / "bridge.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        with pytest.raises(EmailStagingNotFoundError):
            await approve_staged_item(
                conn, staging_id=999, overrides=ApproveOverrides(), force=False
            )


@pytest.mark.asyncio
async def test_approve_staged_item_raises_for_wrong_status(tmp_path: Path) -> None:
    db = tmp_path / "bridge.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _seed_accounts(conn)
        item_id = await _insert_staged(
            conn,
            gmail_message_id="approved-1",
            account_id=ids["Bank"],
            status="approved",
        )

        with pytest.raises(EmailStagingStatusError):
            await approve_staged_item(
                conn, staging_id=item_id, overrides=ApproveOverrides(), force=False
            )


@pytest.mark.asyncio
async def test_approve_staged_item_quarantined_requires_force(tmp_path: Path) -> None:
    db = tmp_path / "bridge.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _seed_accounts(conn)
        item_id = await _insert_staged(
            conn,
            gmail_message_id="q-1",
            account_id=ids["Bank"],
            status="quarantined",
        )

        with pytest.raises(EmailStagingStatusError):
            await approve_staged_item(
                conn, staging_id=item_id, overrides=ApproveOverrides(), force=False
            )

        row = await approve_staged_item(
            conn, staging_id=item_id, overrides=ApproveOverrides(), force=True
        )

    assert row.status == "approved"
    assert row.ledger_transaction_id is not None


@pytest.mark.asyncio
async def test_approve_as_transfer_posts_both_legs(tmp_path: Path) -> None:
    db = tmp_path / "bridge.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _seed_accounts(conn)
        debit_id = await _insert_staged(
            conn, gmail_message_id="xfer-debit", account_id=ids["Bank"]
        )
        credit_id = await _insert_staged(
            conn,
            gmail_message_id="xfer-credit",
            account_id=ids["Bank 2"],
            tx_type="credit",
        )

        debit_row, credit_row, ledger_tx_id = await approve_as_transfer(
            conn,
            debit_id=debit_id,
            credit_id=credit_id,
            overrides=TransferOverrides(),
            force=False,
        )

    assert ledger_tx_id > 0
    assert debit_row.status == "approved"
    assert credit_row.status == "approved"
    assert debit_row.ledger_transaction_id == ledger_tx_id
    assert credit_row.ledger_transaction_id == ledger_tx_id


@pytest.mark.asyncio
async def test_approve_as_transfer_quarantines_soft_duplicate(tmp_path: Path) -> None:
    db = tmp_path / "bridge.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _seed_accounts(conn)
        first_id = await _insert_staged(
            conn, gmail_message_id="xfer-dupe-first", account_id=ids["Bank"]
        )
        await approve_staged_item(
            conn, staging_id=first_id, overrides=ApproveOverrides(), force=False
        )
        debit_id = await _insert_staged(
            conn, gmail_message_id="xfer-dupe-debit", account_id=ids["Bank"]
        )
        credit_id = await _insert_staged(
            conn,
            gmail_message_id="xfer-dupe-credit",
            account_id=ids["Bank 2"],
            tx_type="credit",
        )

        debit_row, credit_row, ledger_tx_id = await approve_as_transfer(
            conn,
            debit_id=debit_id,
            credit_id=credit_id,
            overrides=TransferOverrides(),
            force=False,
        )

    assert ledger_tx_id == 0
    assert debit_row.status == "quarantined"
    assert credit_row.status == "quarantined"
    assert debit_row.intake_candidate_id == credit_row.intake_candidate_id
    assert debit_row.intake_candidate_id is not None


@pytest.mark.asyncio
async def test_approve_as_transfer_force_posts_despite_duplicate(tmp_path: Path) -> None:
    db = tmp_path / "bridge.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _seed_accounts(conn)
        first_id = await _insert_staged(
            conn, gmail_message_id="xfer-force-first", account_id=ids["Bank"]
        )
        await approve_staged_item(
            conn, staging_id=first_id, overrides=ApproveOverrides(), force=False
        )
        debit_id = await _insert_staged(
            conn, gmail_message_id="xfer-force-debit", account_id=ids["Bank"]
        )
        credit_id = await _insert_staged(
            conn,
            gmail_message_id="xfer-force-credit",
            account_id=ids["Bank 2"],
            tx_type="credit",
        )

        debit_row, credit_row, ledger_tx_id = await approve_as_transfer(
            conn,
            debit_id=debit_id,
            credit_id=credit_id,
            overrides=TransferOverrides(),
            force=True,
        )

    assert ledger_tx_id > 0
    assert debit_row.status == "approved"
    assert credit_row.status == "approved"


@pytest.mark.asyncio
async def test_force_approve_updates_existing_quarantine_candidate(tmp_path: Path) -> None:
    db = tmp_path / "bridge-force-update.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _seed_accounts(conn)
        first_id = await _insert_staged(
            conn, gmail_message_id="force-update-1", account_id=ids["Bank"]
        )
        await approve_staged_item(
            conn, staging_id=first_id, overrides=ApproveOverrides(), force=False
        )
        second_id = await _insert_staged(
            conn,
            gmail_message_id="force-update-2",
            account_id=ids["Bank"],
            merchant="Coffee Shop",
        )
        quarantined = await approve_staged_item(
            conn, staging_id=second_id, overrides=ApproveOverrides(), force=False
        )
        candidate_id = quarantined.intake_candidate_id
        assert candidate_id is not None

        await approve_staged_item(
            conn, staging_id=second_id, overrides=ApproveOverrides(), force=True
        )

        cursor = await conn.execute(
            "SELECT status, COUNT(*) FROM intake_candidates WHERE source = 'email' GROUP BY status"
        )
        rows = {status: count for status, count in await cursor.fetchall()}
        candidate = await (
            await conn.execute(
                "SELECT status FROM intake_candidates WHERE id = ?", (candidate_id,)
            )
        ).fetchone()

    assert rows.get("posted") == 2
    assert candidate is not None
    assert candidate[0] == "posted"


@pytest.mark.asyncio
async def test_force_approve_transfer_quarantine_pair_raises(tmp_path: Path) -> None:
    db = tmp_path / "bridge-transfer-q.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _seed_accounts(conn)
        first_id = await _insert_staged(
            conn, gmail_message_id="xfer-q-first", account_id=ids["Bank"]
        )
        await approve_staged_item(
            conn, staging_id=first_id, overrides=ApproveOverrides(), force=False
        )
        debit_id = await _insert_staged(
            conn, gmail_message_id="xfer-q-debit", account_id=ids["Bank"]
        )
        credit_id = await _insert_staged(
            conn,
            gmail_message_id="xfer-q-credit",
            account_id=ids["Bank 2"],
            tx_type="credit",
        )
        debit_row, credit_row, _ = await approve_as_transfer(
            conn,
            debit_id=debit_id,
            credit_id=credit_id,
            overrides=TransferOverrides(),
            force=False,
        )
        assert debit_row.status == "quarantined"
        assert credit_row.status == "quarantined"

        with pytest.raises(EmailStagingStatusError, match="approve-as-transfer with force=true"):
            await approve_staged_item(
                conn,
                staging_id=debit_id,
                overrides=ApproveOverrides(),
                force=True,
            )


@pytest.mark.asyncio
async def test_force_approve_possible_transfer_quarantine_raises(tmp_path: Path) -> None:
    db = tmp_path / "bridge-transfer-single-q.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _seed_accounts(conn)
        item_id = await _insert_staged(
            conn,
            gmail_message_id="xfer-single-q",
            account_id=ids["Bank"],
            raw_snippet="NEFT to self savings account",
        )
        row = await approve_staged_item(
            conn, staging_id=item_id, overrides=ApproveOverrides(), force=False
        )
        assert row.status == "quarantined"

        with pytest.raises(EmailStagingStatusError, match="approve-as-transfer with force=true"):
            await approve_staged_item(
                conn,
                staging_id=item_id,
                overrides=ApproveOverrides(),
                force=True,
            )


@pytest.mark.asyncio
async def test_force_approve_as_transfer_updates_existing_candidate(tmp_path: Path) -> None:
    db = tmp_path / "bridge-transfer-force-update.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _seed_accounts(conn)
        first_id = await _insert_staged(
            conn, gmail_message_id="xfer-force-update-first", account_id=ids["Bank"]
        )
        await approve_staged_item(
            conn, staging_id=first_id, overrides=ApproveOverrides(), force=False
        )
        debit_id = await _insert_staged(
            conn, gmail_message_id="xfer-force-update-debit", account_id=ids["Bank"]
        )
        credit_id = await _insert_staged(
            conn,
            gmail_message_id="xfer-force-update-credit",
            account_id=ids["Bank 2"],
            tx_type="credit",
        )
        debit_row, _, _ = await approve_as_transfer(
            conn,
            debit_id=debit_id,
            credit_id=credit_id,
            overrides=TransferOverrides(),
            force=False,
        )
        candidate_id = debit_row.intake_candidate_id
        assert candidate_id is not None

        await approve_as_transfer(
            conn,
            debit_id=debit_id,
            credit_id=credit_id,
            overrides=TransferOverrides(),
            force=True,
        )

        candidate = await (
            await conn.execute(
                "SELECT status FROM intake_candidates WHERE id = ?", (candidate_id,)
            )
        ).fetchone()
        count = await (
            await conn.execute("SELECT COUNT(*) FROM intake_candidates WHERE source = 'email'")
        ).fetchone()

    assert candidate is not None
    assert candidate[0] == "posted"
    assert count is not None
    assert count[0] == 2


@pytest.mark.asyncio
async def test_approve_as_transfer_raises_when_missing_row(tmp_path: Path) -> None:
    db = tmp_path / "bridge.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _seed_accounts(conn)
        debit_id = await _insert_staged(
            conn, gmail_message_id="xfer-missing", account_id=ids["Bank"]
        )

        with pytest.raises(EmailStagingNotFoundError):
            await approve_as_transfer(
                conn,
                debit_id=debit_id,
                credit_id=999,
                overrides=TransferOverrides(),
                force=False,
            )
