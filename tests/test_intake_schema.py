from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from finance_common.db import ensure_database, schema_sql
from finance_common.db.migrations import apply_migrations


@pytest.mark.asyncio
async def test_intake_tables_exist_after_ensure(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        cur = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('intake_candidates', 'domain_events')"
        )
        names = {r[0] for r in await cur.fetchall()}
        assert names == {"intake_candidates", "domain_events"}

        intake_cols = {
            str(row[1])
            for row in await (await conn.execute("PRAGMA table_info(intake_candidates)")).fetchall()
        }
        assert {
            "id",
            "status",
            "source",
            "external_key",
            "tx_date",
            "amount_paise",
            "direction",
            "payee",
            "narration",
            "suggested_account_id",
            "suggested_counter_account_id",
            "suggested_category",
            "confidence",
            "quarantine_reason",
            "ledger_transaction_id",
            "raw_payload_json",
            "email_staging_id",
            "created_at",
            "updated_at",
        } <= intake_cols

        event_cols = {
            str(row[1])
            for row in await (await conn.execute("PRAGMA table_info(domain_events)")).fetchall()
        }
        assert {"id", "event_type", "payload_json", "created_at"} <= event_cols


@pytest.mark.asyncio
async def test_migrations_add_intake_tables_to_pre_intake_database(tmp_path: Path) -> None:
    db = tmp_path / "old.db"
    async with aiosqlite.connect(db) as conn:
        await conn.executescript(schema_sql())
        await conn.executescript(
            """
            DROP TABLE IF EXISTS intake_candidates;
            DROP TABLE IF EXISTS domain_events;
            """
        )
        await apply_migrations(conn)

        tables = {
            str(row[0])
            for row in await (
                await conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' "
                    "AND name IN ('intake_candidates', 'domain_events')"
                )
            ).fetchall()
        }
        assert tables == {"intake_candidates", "domain_events"}
