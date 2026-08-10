from __future__ import annotations

from datetime import date
from pathlib import Path

import aiosqlite
import pytest

from finance_common.db import ensure_database
from finance_common.intake.models import Candidate
from finance_common.intake.service import Decision, ingest
from finance_common.ledger import service as ledger_service
from finance_common.ledger.models import NewPosting, PostTransactionInput


async def _account_ids(conn: aiosqlite.Connection) -> dict[str, int]:
    await conn.executemany(
        "INSERT INTO accounts (name, type, account_class) VALUES (?, ?, ?)",
        [
            ("Test bank", "savings", "asset_cash"),
            ("Test food", "expense", "expense"),
        ],
    )
    await conn.commit()
    cursor = await conn.execute(
        "SELECT id, name FROM accounts WHERE name IN ('Test bank', 'Test food')"
    )
    return {str(name): int(account_id) for account_id, name in await cursor.fetchall()}


def _candidate(**overrides: object) -> Candidate:
    values: dict[str, object] = {
        "source": "import",
        "tx_date": date(2026, 8, 10),
        "amount_paise": 50_000,
        "direction": "out",
        "suggested_account_id": 1,
        "payee": "Swiggy",
        "narration": "UPI Swiggy",
        "suggested_category": "Food",
        "suggested_counter_account_id": 2,
        "external_key": "import:row-1",
        "confidence": 0.95,
    }
    values.update(overrides)
    return Candidate(**values)  # type: ignore[arg-type]


async def _candidate_row(conn: aiosqlite.Connection, candidate_id: int) -> tuple[object, ...]:
    cursor = await conn.execute(
        """
        SELECT status, quarantine_reason, ledger_transaction_id
        FROM intake_candidates WHERE id = ?
        """,
        (candidate_id,),
    )
    row = await cursor.fetchone()
    assert row is not None
    return tuple(row)


@pytest.mark.asyncio
async def test_ingest_returns_noop_for_existing_posted_external_key(tmp_path: Path) -> None:
    db = tmp_path / "intake.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)
        existing_tx_id = await ledger_service.post(
            conn,
            PostTransactionInput(
                tx_date=date(2026, 8, 10),
                postings=(
                    NewPosting(ids["Test food"], 50_000, "Food"),
                    NewPosting(ids["Test bank"], -50_000),
                ),
                external_key="import:row-1",
            ),
        )

        decision, result_id = await ingest(
            conn,
            _candidate(
                suggested_account_id=ids["Test bank"],
                suggested_counter_account_id=ids["Test food"],
            ),
        )

    assert (decision, result_id) == (Decision.NOOP, existing_tx_id)


@pytest.mark.asyncio
async def test_ingest_quarantines_candidate_without_account(tmp_path: Path) -> None:
    db = tmp_path / "intake.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        decision, candidate_id = await ingest(conn, _candidate(suggested_account_id=None))
        assert candidate_id is not None
        assert await _candidate_row(conn, candidate_id) == (
            "pending",
            "missing_account",
            None,
        )
        event = await (
            await conn.execute("SELECT event_type, payload_json FROM domain_events")
        ).fetchone()

    assert decision is Decision.QUARANTINED
    assert event is not None
    assert tuple(event)[0] == "intake.quarantine_created"
    assert '"reason": "missing_account"' in str(tuple(event)[1])


@pytest.mark.asyncio
async def test_ingest_quarantines_possible_duplicate(tmp_path: Path) -> None:
    db = tmp_path / "intake.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)
        await conn.execute(
            """
            INSERT INTO intake_candidates (
                status, source, tx_date, amount_paise, direction, payee,
                suggested_account_id
            ) VALUES ('pending', 'import', '2026-08-09', 50000, 'out', 'Swiggy', ?)
            """,
            (ids["Test bank"],),
        )
        await conn.commit()

        decision, candidate_id = await ingest(
            conn,
            _candidate(
                suggested_account_id=ids["Test bank"],
                suggested_counter_account_id=ids["Test food"],
                external_key="import:row-2",
            ),
        )

        assert candidate_id is not None
        assert await _candidate_row(conn, candidate_id) == (
            "pending",
            "possible_duplicate",
            None,
        )

    assert decision is Decision.QUARANTINED


@pytest.mark.asyncio
async def test_ingest_quarantines_possible_transfer(tmp_path: Path) -> None:
    db = tmp_path / "intake.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)
        decision, candidate_id = await ingest(
            conn,
            _candidate(
                suggested_account_id=ids["Test bank"],
                suggested_counter_account_id=ids["Test food"],
                narration="NEFT to MY SAVINGS",
            ),
        )

        assert candidate_id is not None
        assert await _candidate_row(conn, candidate_id) == (
            "pending",
            "possible_transfer",
            None,
        )

    assert decision is Decision.QUARANTINED


@pytest.mark.asyncio
async def test_ingest_quarantines_low_confidence(tmp_path: Path) -> None:
    db = tmp_path / "intake.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)
        decision, candidate_id = await ingest(
            conn,
            _candidate(
                suggested_account_id=ids["Test bank"],
                suggested_counter_account_id=ids["Test food"],
                confidence=0.84,
            ),
        )

        assert candidate_id is not None
        assert await _candidate_row(conn, candidate_id) == (
            "pending",
            "low_confidence",
            None,
        )

    assert decision is Decision.QUARANTINED


@pytest.mark.asyncio
async def test_ingest_posts_high_confidence_candidate(tmp_path: Path) -> None:
    db = tmp_path / "intake.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _account_ids(conn)
        decision, ledger_transaction_id = await ingest(
            conn,
            _candidate(
                suggested_account_id=ids["Test bank"],
                suggested_counter_account_id=ids["Test food"],
            ),
        )

        assert ledger_transaction_id is not None
        cursor = await conn.execute(
            """
            SELECT status, quarantine_reason, ledger_transaction_id
            FROM intake_candidates WHERE external_key = 'import:row-1'
            """
        )
        candidate = await cursor.fetchone()
        assert candidate is not None
        assert tuple(candidate) == ("posted", None, ledger_transaction_id)

    assert decision is Decision.POSTED
