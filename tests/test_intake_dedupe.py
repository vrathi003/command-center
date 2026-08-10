from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import aiosqlite
import pytest

from finance_common.db import ensure_database
from finance_common.intake.dedupe import find_soft_duplicate, make_external_key
from finance_common.ledger import service as ledger_service
from finance_common.ledger.models import NewPosting, PostTransactionInput


def test_make_external_key_uses_provider_id_when_present() -> None:
    key = make_external_key(
        source="import",
        provider_id="row-42",
        date="2026-08-10",
        amount_paise=12_345,
        narration="UPI/SWIGGY",
        account_id=7,
    )
    assert key == "import:row-42"


def test_make_external_key_is_stable_for_same_fingerprint() -> None:
    kwargs = {
        "source": "import",
        "provider_id": None,
        "date": "2026-08-10",
        "amount_paise": 12_345,
        "narration": "UPI/SWIGGY",
        "account_id": 7,
    }
    assert make_external_key(**kwargs) == make_external_key(**kwargs)


def test_make_external_key_changes_when_fingerprint_changes() -> None:
    base = {
        "source": "import",
        "provider_id": None,
        "date": "2026-08-10",
        "amount_paise": 12_345,
        "narration": "UPI/SWIGGY",
        "account_id": 7,
    }
    key_a = make_external_key(**base)
    key_b = make_external_key(**{**base, "amount_paise": 12_346})
    assert key_a != key_b
    assert key_a.startswith("import:")
    assert key_b.startswith("import:")


def test_make_external_key_hash_ignores_whitespace_in_narration() -> None:
    base = {
        "source": "import",
        "provider_id": None,
        "date": "2026-08-10",
        "amount_paise": 12_345,
        "account_id": 7,
    }
    assert make_external_key(**base, narration="  UPI/SWIGGY  ") == make_external_key(
        **base, narration="UPI/SWIGGY"
    )


async def _bank_account_id(conn: aiosqlite.Connection) -> int:
    await conn.execute(
        "INSERT INTO accounts (name, type, account_class) VALUES ('Bank', 'savings', 'asset_cash')"
    )
    await conn.execute(
        "INSERT INTO accounts (name, type, account_class) VALUES ('Food', 'expense', 'expense')"
    )
    await conn.commit()
    cursor = await conn.execute("SELECT id FROM accounts WHERE name = 'Bank'")
    row = await cursor.fetchone()
    assert row is not None
    return int(row[0])


@pytest.mark.asyncio
async def test_find_soft_duplicate_matches_intake_candidate_within_window(
    tmp_path: Path,
) -> None:
    db = tmp_path / "dedupe.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        account_id = await _bank_account_id(conn)
        await conn.execute(
            """
            INSERT INTO intake_candidates (
                status, source, tx_date, amount_paise, direction,
                payee, suggested_account_id
            ) VALUES ('pending', 'import', '2026-08-09', 50000, 'out', 'Swiggy India', ?)
            """,
            (account_id,),
        )
        await conn.commit()

        match_id = await find_soft_duplicate(
            conn,
            account_id=account_id,
            amount_paise=50_000,
            tx_date=date(2026, 8, 10),
            payee="SWIGGY INDIA PVT",
            window_days=1,
        )

    assert match_id == 1


@pytest.mark.asyncio
async def test_find_soft_duplicate_returns_none_outside_window(tmp_path: Path) -> None:
    db = tmp_path / "dedupe.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        account_id = await _bank_account_id(conn)
        await conn.execute(
            """
            INSERT INTO intake_candidates (
                status, source, tx_date, amount_paise, direction,
                payee, suggested_account_id
            ) VALUES ('pending', 'import', '2026-08-01', 50000, 'out', 'Swiggy', ?)
            """,
            (account_id,),
        )
        await conn.commit()

        match_id = await find_soft_duplicate(
            conn,
            account_id=account_id,
            amount_paise=50_000,
            tx_date=date(2026, 8, 10),
            payee="Swiggy",
            window_days=1,
        )

    assert match_id is None


@pytest.mark.asyncio
async def test_find_soft_duplicate_matches_posted_ledger_transaction(
    tmp_path: Path,
) -> None:
    db = tmp_path / "dedupe.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        account_id = await _bank_account_id(conn)
        cursor = await conn.execute("SELECT id FROM accounts WHERE name = 'Food'")
        expense_id = int((await cursor.fetchone())[0])
        tx_id = await ledger_service.post(
            conn,
            PostTransactionInput(
                tx_date=date(2026, 8, 10),
                payee="Amazon Pay",
                postings=(
                    NewPosting(expense_id, 25_000, "Shopping"),
                    NewPosting(account_id, -25_000),
                ),
                source="manual",
            ),
        )

        match_id = await find_soft_duplicate(
            conn,
            account_id=account_id,
            amount_paise=25_000,
            tx_date=date(2026, 8, 10) + timedelta(days=1),
            payee="amazon pay india",
            window_days=1,
        )

    assert match_id == tx_id


@pytest.mark.asyncio
async def test_find_soft_duplicate_ignores_void_ledger_transactions(tmp_path: Path) -> None:
    db = tmp_path / "dedupe.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        account_id = await _bank_account_id(conn)
        cursor = await conn.execute("SELECT id FROM accounts WHERE name = 'Food'")
        expense_id = int((await cursor.fetchone())[0])
        tx_id = await ledger_service.post(
            conn,
            PostTransactionInput(
                tx_date=date(2026, 8, 10),
                payee="Netflix",
                postings=(
                    NewPosting(expense_id, 79900, "Entertainment"),
                    NewPosting(account_id, -79_900),
                ),
                source="manual",
            ),
        )
        await ledger_service.void(conn, tx_id)

        match_id = await find_soft_duplicate(
            conn,
            account_id=account_id,
            amount_paise=79_900,
            tx_date=date(2026, 8, 10),
            payee="Netflix",
            window_days=1,
        )

    assert match_id is None
