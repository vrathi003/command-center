from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from finance_common.db import ensure_database, schema_sql
from finance_common.db.migrations import apply_migrations


@pytest.mark.asyncio
async def test_alert_notifications_and_processed_at_exist(tmp_path: Path) -> None:
    db = tmp_path / "alerts.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        cols = {
            r[1]
            for r in await (
                await conn.execute("PRAGMA table_info(domain_events)")
            ).fetchall()
        }
        assert "processed_at" in cols
        names = {
            r[0]
            for r in await (
                await conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name='alert_notifications'"
                )
            ).fetchall()
        }
        assert "alert_notifications" in names
        acol = {
            r[1]
            for r in await (
                await conn.execute("PRAGMA table_info(alert_notifications)")
            ).fetchall()
        }
        assert {
            "id", "event_id", "event_type", "fingerprint", "kind",
            "title", "message", "severity", "status", "created_at", "acked_at",
        } <= acol


@pytest.mark.asyncio
async def test_migrations_add_processed_at_to_existing_domain_events(tmp_path: Path) -> None:
    db = tmp_path / "old.db"
    async with aiosqlite.connect(db) as conn:
        await conn.executescript(schema_sql())
        await conn.executescript(
            """
            DROP TABLE IF EXISTS alert_notifications;
            DROP TABLE IF EXISTS domain_events;
            CREATE TABLE domain_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        await apply_migrations(conn)

        cols = {
            str(r[1])
            for r in await (await conn.execute("PRAGMA table_info(domain_events)")).fetchall()
        }
        assert "processed_at" in cols

        names = {
            str(r[0])
            for r in await (
                await conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name='alert_notifications'"
                )
            ).fetchall()
        }
        assert "alert_notifications" in names
