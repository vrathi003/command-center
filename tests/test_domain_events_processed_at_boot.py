"""Existing domain_events without processed_at must boot via ensure_database."""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from finance_common.db import ensure_database


@pytest.mark.asyncio
async def test_ensure_database_upgrades_domain_events_processed_at(tmp_path: Path) -> None:
    db = tmp_path / "legacy_events.db"
    await ensure_database(db)

    async with aiosqlite.connect(db) as conn:
        await conn.executescript(
            """
            DROP INDEX IF EXISTS idx_domain_events_unprocessed;
            CREATE TABLE domain_events_legacy (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            INSERT INTO domain_events_legacy (id, event_type, payload_json, created_at)
            SELECT id, event_type, payload_json, created_at FROM domain_events;
            DROP TABLE domain_events;
            ALTER TABLE domain_events_legacy RENAME TO domain_events;
            """
        )
        await conn.commit()
        cols = {str(r[1]) for r in await (await conn.execute("PRAGMA table_info(domain_events)")).fetchall()}
        assert "processed_at" not in cols

    await ensure_database(db)

    async with aiosqlite.connect(db) as conn:
        cols = {str(r[1]) for r in await (await conn.execute("PRAGMA table_info(domain_events)")).fetchall()}
        assert "processed_at" in cols
