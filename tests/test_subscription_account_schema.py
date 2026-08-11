"""Subscriptions table account_id column."""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest
from starlette.testclient import TestClient

from finance_common.db import ensure_database
from finance_common.db.migrations import apply_migrations


async def _subscription_columns(conn: aiosqlite.Connection) -> set[str]:
    cur = await conn.execute("PRAGMA table_info(subscriptions)")
    return {str(r[1]) for r in await cur.fetchall()}


@pytest.mark.asyncio
async def test_fresh_schema_has_subscription_account_id(tmp_path: Path) -> None:
    db = tmp_path / "fresh.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        cols = await _subscription_columns(conn)
        assert "account_id" in cols


@pytest.mark.asyncio
async def test_migrations_add_subscription_account_id(tmp_path: Path) -> None:
    """Legacy DB without account_id picks it up via apply_migrations."""
    db = tmp_path / "legacy.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        await conn.executescript(
            """
            CREATE TABLE subscriptions_legacy AS SELECT
                id, name, provider, category, amount_paise, billing_cycle,
                next_billing_date, notes, is_active, created_at, updated_at
            FROM subscriptions;
            DROP TABLE subscriptions;
            CREATE TABLE subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                provider TEXT,
                category TEXT,
                amount_paise INTEGER NOT NULL,
                billing_cycle TEXT NOT NULL DEFAULT 'monthly',
                next_billing_date TEXT,
                notes TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            INSERT INTO subscriptions SELECT * FROM subscriptions_legacy;
            DROP TABLE subscriptions_legacy;
            """
        )
        await conn.commit()

        before = await _subscription_columns(conn)
        assert "account_id" not in before

        await apply_migrations(conn)
        after = await _subscription_columns(conn)
        assert "account_id" in after


def test_create_subscription_with_account_id_round_trip(api_client: TestClient) -> None:
    bank = api_client.post(
        "/api/accounts/",
        json={"name": "HDFC Savings", "type": "savings", "account_class": "asset_cash"},
    )
    assert bank.status_code == 201, bank.text
    account_id = int(bank.json()["id"])

    created = api_client.post(
        "/api/subscriptions/",
        json={
            "name": "Netflix",
            "amount_paise": 649_00,
            "billing_cycle": "monthly",
            "account_id": account_id,
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["account_id"] == account_id
    sub_id = int(body["id"])

    fetched = api_client.get(f"/api/subscriptions/{sub_id}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["account_id"] == account_id
