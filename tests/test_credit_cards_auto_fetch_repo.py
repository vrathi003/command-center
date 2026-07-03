"""Repository-level tests for the auto-fetch columns/lookups added to credit_cards."""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from finance_common.config import AppSettings
from finance_common.db import ensure_database, open_db
from finance_common.repositories import credit_cards as cc_repo

# Shape of credit_card_statements before source/gmail_message_id existed — every real
# on-disk DB predates these columns, so `ensure_database` must upgrade it without error.
_PRE_MIGRATION_SCHEMA = """
CREATE TABLE credit_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    issuer TEXT,
    last_four TEXT,
    credit_limit_paise INTEGER NOT NULL,
    current_balance_paise INTEGER,
    notes TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE credit_card_statements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    credit_card_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    period_start TEXT,
    period_end TEXT,
    extraction_preview TEXT,
    summary_json TEXT,
    line_items_json TEXT,
    status TEXT NOT NULL DEFAULT 'pending_review',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (credit_card_id) REFERENCES credit_cards(id) ON DELETE CASCADE
);
"""


@pytest.mark.asyncio
async def test_ensure_database_upgrades_pre_existing_credit_card_statements_table(
    tmp_path: Path,
) -> None:
    """Regression test: `ensure_database` must not crash on a real (pre-migration)
    on-disk DB — this is exactly what runs on every API startup against the user's
    actual database, not just fresh test DBs."""
    db_path = tmp_path / "old_shape.db"
    async with aiosqlite.connect(db_path) as conn:
        await conn.executescript(_PRE_MIGRATION_SCHEMA)
        await conn.commit()

    await ensure_database(db_path)  # must not raise

    async with open_db(db_path) as conn:
        cid = await cc_repo.insert_credit_card(
            conn,
            name="Upgraded Card",
            issuer="HDFC Bank",
            last_four="9999",
            credit_limit_paise=10_000,
            current_balance_paise=None,
            notes=None,
            auto_fetch_enabled=True,
        )
        row = await cc_repo.get_credit_card(conn, cid)
        assert row is not None
        assert row.auto_fetch_enabled is True


@pytest.mark.asyncio
async def test_find_credit_card_by_last_four() -> None:
    settings = AppSettings()
    await ensure_database(settings.db_path)
    async with open_db(settings.db_path) as conn:
        cid = await cc_repo.insert_credit_card(
            conn,
            name="Test ICICI",
            issuer="ICICI Bank",
            last_four="5678",
            credit_limit_paise=50_000,
            current_balance_paise=None,
            notes=None,
        )
        found = await cc_repo.find_credit_card_by_last_four(conn, "5678")
        assert found is not None
        assert found.id == cid

        found_with_issuer = await cc_repo.find_credit_card_by_last_four(
            conn, "5678", issuer_hint="icici"
        )
        assert found_with_issuer is not None
        assert found_with_issuer.id == cid

        assert await cc_repo.find_credit_card_by_last_four(conn, "0000") is None


@pytest.mark.asyncio
async def test_list_auto_fetch_enabled_cards_filters_correctly() -> None:
    settings = AppSettings()
    await ensure_database(settings.db_path)
    async with open_db(settings.db_path) as conn:
        await cc_repo.insert_credit_card(
            conn,
            name="Disabled Card",
            issuer="HDFC Bank",
            last_four="1111",
            credit_limit_paise=10_000,
            current_balance_paise=None,
            notes=None,
            auto_fetch_enabled=False,
        )
        enabled_id = await cc_repo.insert_credit_card(
            conn,
            name="Enabled Card",
            issuer="HDFC Bank",
            last_four="2222",
            credit_limit_paise=10_000,
            current_balance_paise=None,
            notes=None,
            auto_fetch_enabled=True,
            statement_pdf_password="secret",
        )
        rows = await cc_repo.list_auto_fetch_enabled_cards(conn)
        assert [r.id for r in rows] == [enabled_id]
        assert rows[0].statement_pdf_password == "secret"


@pytest.mark.asyncio
async def test_statement_dedup_and_recent_listing() -> None:
    settings = AppSettings()
    await ensure_database(settings.db_path)
    async with open_db(settings.db_path) as conn:
        cid = await cc_repo.insert_credit_card(
            conn,
            name="Test SBI",
            issuer="SBI",
            last_four="3333",
            credit_limit_paise=10_000,
            current_balance_paise=None,
            notes=None,
        )
        sid = await cc_repo.insert_statement(
            conn,
            credit_card_id=cid,
            filename="a.pdf",
            period_start=None,
            period_end=None,
            extraction_preview=None,
            summary_json="{}",
            line_items_json="[]",
            source="auto_fetch",
            gmail_message_id="msg-abc",
        )

        dup = await cc_repo.get_statement_by_gmail_message_id(conn, "msg-abc")
        assert dup is not None
        assert dup.id == sid

        with pytest.raises(Exception):  # noqa: B017 - sqlite3.IntegrityError via aiosqlite
            await cc_repo.insert_statement(
                conn,
                credit_card_id=cid,
                filename="b.pdf",
                period_start=None,
                period_end=None,
                extraction_preview=None,
                summary_json="{}",
                line_items_json="[]",
                source="auto_fetch",
                gmail_message_id="msg-abc",
            )

        recent = await cc_repo.list_recent_statements(conn, limit=10)
        assert any(r.id == sid for r in recent)
