"""Investments and fixed_income table account_id columns."""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from finance_common.db import ensure_database
from finance_common.db.migrations import apply_migrations


async def _investment_columns(conn: aiosqlite.Connection) -> set[str]:
    cur = await conn.execute("PRAGMA table_info(investments)")
    return {str(r[1]) for r in await cur.fetchall()}


async def _fixed_income_columns(conn: aiosqlite.Connection) -> set[str]:
    cur = await conn.execute("PRAGMA table_info(fixed_income)")
    return {str(r[1]) for r in await cur.fetchall()}


@pytest.mark.asyncio
async def test_fresh_schema_has_investment_account_id_columns(tmp_path: Path) -> None:
    db = tmp_path / "fresh.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        inv_cols = await _investment_columns(conn)
        fi_cols = await _fixed_income_columns(conn)
        assert "account_id" in inv_cols
        assert "account_id" in fi_cols


@pytest.mark.asyncio
async def test_migrations_add_investment_account_id_columns(tmp_path: Path) -> None:
    """Legacy DB without account_id picks it up via apply_migrations."""
    db = tmp_path / "legacy.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        await conn.executescript(
            """
            CREATE TABLE investments_legacy AS SELECT
                id, instrument, type, isin_code, units, avg_price_paise,
                current_price_paise, last_synced, sector, equity_tax_class,
                created_at, updated_at
            FROM investments;
            DROP TABLE investments;
            CREATE TABLE investments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instrument TEXT NOT NULL,
                type TEXT NOT NULL,
                isin_code TEXT,
                units REAL,
                avg_price_paise INTEGER,
                current_price_paise INTEGER,
                last_synced TEXT,
                sector TEXT,
                equity_tax_class TEXT DEFAULT 'unspecified',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            INSERT INTO investments SELECT * FROM investments_legacy;
            DROP TABLE investments_legacy;

            CREATE TABLE fixed_income_legacy AS SELECT
                id, institution, type, principal_paise, rate_percent,
                start_date, maturity_date, created_at, updated_at
            FROM fixed_income;
            DROP TABLE fixed_income;
            CREATE TABLE fixed_income (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                institution TEXT NOT NULL,
                type TEXT NOT NULL,
                principal_paise INTEGER NOT NULL,
                rate_percent REAL,
                start_date TEXT,
                maturity_date TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            INSERT INTO fixed_income SELECT * FROM fixed_income_legacy;
            DROP TABLE fixed_income_legacy;
            """
        )
        await conn.commit()

        before_inv = await _investment_columns(conn)
        before_fi = await _fixed_income_columns(conn)
        assert "account_id" not in before_inv
        assert "account_id" not in before_fi

        await apply_migrations(conn)
        after_inv = await _investment_columns(conn)
        after_fi = await _fixed_income_columns(conn)
        assert "account_id" in after_inv
        assert "account_id" in after_fi
