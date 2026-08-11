"""Debts table account link columns (account_id, payment_account_id)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import aiosqlite
import pytest

from finance_common.db import ensure_database
from finance_common.db.migrations import apply_migrations
from finance_common.repositories import debts as debt_repo


async def _debt_columns(conn: aiosqlite.Connection) -> set[str]:
    cur = await conn.execute("PRAGMA table_info(debts)")
    return {str(r[1]) for r in await cur.fetchall()}


async def _insert_account(conn: aiosqlite.Connection, name: str) -> int:
    cur = await conn.execute(
        """
        INSERT INTO accounts (name, type, institution, currency, account_class)
        VALUES (?, 'savings', 'Test Bank', 'INR', 'asset_cash')
        """,
        (name,),
    )
    await conn.commit()
    assert cur.lastrowid is not None
    return int(cur.lastrowid)


@pytest.mark.asyncio
async def test_fresh_schema_has_debt_account_link_columns(tmp_path: Path) -> None:
    db = tmp_path / "fresh.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        cols = await _debt_columns(conn)
        assert {"account_id", "payment_account_id"} <= cols


@pytest.mark.asyncio
async def test_migrations_add_debt_account_link_columns(tmp_path: Path) -> None:
    """Legacy DB without account link columns picks them up via apply_migrations."""
    db = tmp_path / "legacy.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        await conn.executescript(
            """
            CREATE TABLE debts_legacy AS SELECT
                id, name, lender, type, original_amount_paise,
                current_balance_paise, emi_paise, rate_percent, start_date,
                next_emi_date, status, created_at, updated_at,
                tenure_months, first_emi_date, full_emi_start_date
            FROM debts;
            DROP TABLE debts;
            CREATE TABLE debts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                lender TEXT,
                type TEXT NOT NULL,
                original_amount_paise INTEGER,
                current_balance_paise INTEGER NOT NULL,
                emi_paise INTEGER,
                rate_percent REAL,
                start_date TEXT,
                next_emi_date TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                tenure_months INTEGER,
                first_emi_date TEXT,
                full_emi_start_date TEXT
            );
            INSERT INTO debts SELECT * FROM debts_legacy;
            DROP TABLE debts_legacy;
            """
        )
        await conn.commit()

        before = await _debt_columns(conn)
        assert "account_id" not in before
        assert "payment_account_id" not in before

        await apply_migrations(conn)
        after = await _debt_columns(conn)
        assert {"account_id", "payment_account_id"} <= after


@pytest.mark.asyncio
async def test_debt_repo_round_trips_account_link_columns(tmp_path: Path) -> None:
    db = tmp_path / "repo.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        await conn.execute("PRAGMA foreign_keys = ON")
        loan_acct = await _insert_account(conn, "Home Loan Liability")
        pay_acct = await _insert_account(conn, "HDFC Savings")

        debt_id = await debt_repo.insert_debt(
            conn,
            name="Home Loan",
            lender="HDFC",
            type_="Home Loan",
            original_amount_paise=5_000_000_00,
            current_balance_paise=4_800_000_00,
            emi_paise=45_000_00,
            rate_percent=8.5,
            start_date="2024-04-01",
            next_emi_date="2026-04-01",
            account_id=loan_acct,
            payment_account_id=pay_acct,
        )

        row = await debt_repo.get_debt(conn, debt_id)
        assert row is not None
        assert row.account_id == loan_acct
        assert row.payment_account_id == pay_acct

        other_pay = await _insert_account(conn, "ICICI Savings")
        updated = replace(row, payment_account_id=other_pay)
        await debt_repo.update_debt_row(conn, updated)
        again = await debt_repo.get_debt(conn, debt_id)
        assert again is not None
        assert again.account_id == loan_acct
        assert again.payment_account_id == other_pay
