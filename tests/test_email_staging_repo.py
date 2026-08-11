"""Repository tests for email_staging candidate link and reset helpers."""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from finance_common.db import ensure_database
from finance_common.repositories import email_staging as staging_repo


async def _insert_candidate(conn: aiosqlite.Connection) -> int:
    cur = await conn.execute(
        """
        INSERT INTO intake_candidates (
            status, source, tx_date, amount_paise, direction
        ) VALUES ('pending', 'email', '2026-08-01', 10000, 'out')
        """
    )
    candidate_id = cur.lastrowid
    assert candidate_id is not None
    await conn.commit()
    return int(candidate_id)


async def _insert_staged(
    conn: aiosqlite.Connection,
    *,
    gmail_message_id: str,
    status: str = "pending",
    created_transaction_id: int | None = None,
    ledger_transaction_id: int | None = None,
    intake_candidate_id: int | None = None,
) -> int:
    cur = await conn.execute(
        """
        INSERT INTO email_transaction_staging (
            gmail_message_id, email_date, status,
            created_transaction_id, ledger_transaction_id, intake_candidate_id
        ) VALUES (?, '2026-08-01', ?, ?, ?, ?)
        """,
        (
            gmail_message_id,
            status,
            created_transaction_id,
            ledger_transaction_id,
            intake_candidate_id,
        ),
    )
    item_id = cur.lastrowid
    assert item_id is not None
    await conn.commit()
    return int(item_id)


@pytest.mark.asyncio
async def test_staged_row_includes_intake_candidate_id(tmp_path: Path) -> None:
    db = tmp_path / "repo.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        candidate_id = await _insert_candidate(conn)
        item_id = await _insert_staged(
            conn,
            gmail_message_id="row-fields-1",
            status="quarantined",
            intake_candidate_id=candidate_id,
        )

        row = await staging_repo.get_staged(conn, item_id)

        assert row is not None
        assert row.intake_candidate_id == candidate_id
        assert row.status == "quarantined"


@pytest.mark.asyncio
async def test_set_status_persists_intake_candidate_id(tmp_path: Path) -> None:
    db = tmp_path / "repo.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        candidate_id = await _insert_candidate(conn)
        item_id = await _insert_staged(conn, gmail_message_id="set-status-1")

        await staging_repo.set_status(
            conn,
            item_id,
            "quarantined",
            intake_candidate_id=candidate_id,
        )

        row = await staging_repo.get_staged(conn, item_id)
        assert row is not None
        assert row.status == "quarantined"
        assert row.intake_candidate_id == candidate_id


@pytest.mark.asyncio
async def test_get_by_intake_candidate_id_returns_linked_rows(tmp_path: Path) -> None:
    db = tmp_path / "repo.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        candidate_id = await _insert_candidate(conn)
        debit_id = await _insert_staged(
            conn,
            gmail_message_id="transfer-debit",
            status="quarantined",
            intake_candidate_id=candidate_id,
        )
        credit_id = await _insert_staged(
            conn,
            gmail_message_id="transfer-credit",
            status="quarantined",
            intake_candidate_id=candidate_id,
        )
        await _insert_staged(conn, gmail_message_id="unrelated")

        rows = await staging_repo.get_by_intake_candidate_id(conn, candidate_id)

        assert {row.id for row in rows} == {debit_id, credit_id}


@pytest.mark.asyncio
async def test_reset_by_transaction_ids_clears_ledger_and_candidate_links(
    tmp_path: Path,
) -> None:
    db = tmp_path / "repo.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        candidate_id = await _insert_candidate(conn)
        legacy_tx_id = 42
        ledger_tx_id = 99
        item_id = await _insert_staged(
            conn,
            gmail_message_id="legacy-reset-1",
            status="approved",
            created_transaction_id=legacy_tx_id,
            ledger_transaction_id=ledger_tx_id,
            intake_candidate_id=candidate_id,
        )

        reset_count = await staging_repo.reset_by_transaction_ids(conn, [legacy_tx_id])

        assert reset_count == 1
        row = await staging_repo.get_staged(conn, item_id)
        assert row is not None
        assert row.status == "pending"
        assert row.created_transaction_id is None
        assert row.ledger_transaction_id is None
        assert row.intake_candidate_id is None


@pytest.mark.asyncio
async def test_reset_by_ledger_transaction_ids_clears_links(tmp_path: Path) -> None:
    db = tmp_path / "repo.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        candidate_id = await _insert_candidate(conn)
        ledger_tx_id = 77
        item_id = await _insert_staged(
            conn,
            gmail_message_id="ledger-reset-1",
            status="approved",
            ledger_transaction_id=ledger_tx_id,
            intake_candidate_id=candidate_id,
        )

        reset_count = await staging_repo.reset_by_ledger_transaction_ids(
            conn, [ledger_tx_id]
        )

        assert reset_count == 1
        row = await staging_repo.get_staged(conn, item_id)
        assert row is not None
        assert row.status == "pending"
        assert row.ledger_transaction_id is None
        assert row.intake_candidate_id is None


@pytest.mark.asyncio
async def test_reset_helpers_noop_on_empty_id_list(tmp_path: Path) -> None:
    db = tmp_path / "repo.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        assert await staging_repo.reset_by_transaction_ids(conn, []) == 0
        assert await staging_repo.reset_by_ledger_transaction_ids(conn, []) == 0
