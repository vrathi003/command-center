"""Schema tests for email_transaction_staging quarantine link."""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from finance_common.db import ensure_database, schema_sql
from finance_common.db.migrations import apply_migrations

_VALID_STAGING_STATUSES = ("pending", "approved", "rejected", "quarantined")


@pytest.mark.asyncio
async def test_email_staging_has_intake_candidate_id_after_ensure(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        cols = {
            str(row[1])
            for row in await (
                await conn.execute("PRAGMA table_info(email_transaction_staging)")
            ).fetchall()
        }
        assert "intake_candidate_id" in cols


@pytest.mark.asyncio
async def test_email_staging_accepts_quarantined_status_and_candidate_link(
    tmp_path: Path,
) -> None:
    db = tmp_path / "t.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        await conn.execute("PRAGMA foreign_keys = ON")
        cur = await conn.execute(
            """
            INSERT INTO intake_candidates (
                status, source, tx_date, amount_paise, direction
            ) VALUES ('pending', 'email', '2026-08-01', 10000, 'out')
            """
        )
        candidate_id = cur.lastrowid
        assert candidate_id is not None
        await conn.execute(
            """
            INSERT INTO email_transaction_staging (
                gmail_message_id, email_date, status, intake_candidate_id
            ) VALUES ('msg-quarantine-1', '2026-08-01', 'quarantined', ?)
            """,
            (candidate_id,),
        )
        row = await (
            await conn.execute(
                """
                SELECT status, intake_candidate_id
                FROM email_transaction_staging
                WHERE gmail_message_id = 'msg-quarantine-1'
                """
            )
        ).fetchone()
        assert row == ("quarantined", candidate_id)
        await conn.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", _VALID_STAGING_STATUSES)
async def test_email_staging_accepts_documented_status_values(
    tmp_path: Path, status: str
) -> None:
    db = tmp_path / "t.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        await conn.execute(
            """
            INSERT INTO email_transaction_staging (
                gmail_message_id, email_date, status
            ) VALUES (?, '2026-08-01', ?)
            """,
            (f"msg-status-{status}", status),
        )
        stored = await (
            await conn.execute(
                "SELECT status FROM email_transaction_staging WHERE gmail_message_id = ?",
                (f"msg-status-{status}",),
            )
        ).fetchone()
        assert stored == (status,)
        await conn.commit()


@pytest.mark.asyncio
async def test_migrations_add_intake_candidate_id_to_existing_staging(
    tmp_path: Path,
) -> None:
    db = tmp_path / "old.db"
    async with aiosqlite.connect(db) as conn:
        await conn.executescript(schema_sql())
        await conn.execute(
            "ALTER TABLE email_transaction_staging DROP COLUMN intake_candidate_id"
        )
        await conn.commit()
        cols_before = {
            str(row[1])
            for row in await (
                await conn.execute("PRAGMA table_info(email_transaction_staging)")
            ).fetchall()
        }
        assert "intake_candidate_id" not in cols_before

        await apply_migrations(conn)

        cols_after = {
            str(row[1])
            for row in await (
                await conn.execute("PRAGMA table_info(email_transaction_staging)")
            ).fetchall()
        }
        assert "intake_candidate_id" in cols_after
