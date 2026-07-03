"""merchant_rules table creation + one-time heuristic seed."""

from __future__ import annotations

import pytest

from finance_common.config import AppSettings
from finance_common.db import ensure_database, open_db


@pytest.mark.asyncio
async def test_merchant_rules_table_created_and_seeded() -> None:
    settings = AppSettings()
    await ensure_database(settings.db_path)

    async with open_db(settings.db_path) as conn:
        cur = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='merchant_rules'"
        )
        assert await cur.fetchone() is not None

        cur = await conn.execute("SELECT COUNT(*) FROM merchant_rules")
        row = await cur.fetchone()
        assert row is not None
        assert row[0] > 0

        cur = await conn.execute(
            "SELECT category, source, confidence FROM merchant_rules "
            "WHERE match_value = 'bigbasket'"
        )
        seeded = await cur.fetchone()
        assert seeded is not None
        assert seeded[0] == "Groceries"
        assert seeded[1] == "heuristic"
        assert seeded[2] == pytest.approx(0.6)


@pytest.mark.asyncio
async def test_seed_never_inserts_other_category() -> None:
    settings = AppSettings()
    await ensure_database(settings.db_path)

    async with open_db(settings.db_path) as conn:
        cur = await conn.execute(
            "SELECT COUNT(*) FROM merchant_rules WHERE source = 'heuristic' AND category = 'Other'"
        )
        row = await cur.fetchone()
        assert row is not None
        assert row[0] == 0


@pytest.mark.asyncio
async def test_seed_is_idempotent_on_repeat_migration() -> None:
    settings = AppSettings()
    await ensure_database(settings.db_path)
    async with open_db(settings.db_path) as conn:
        cur = await conn.execute("SELECT COUNT(*) FROM merchant_rules")
        first_count = (await cur.fetchone())[0]  # type: ignore[index]

    # Re-running ensure_database (as happens on every app startup) must not duplicate seed rows.
    await ensure_database(settings.db_path)
    async with open_db(settings.db_path) as conn:
        cur = await conn.execute("SELECT COUNT(*) FROM merchant_rules")
        second_count = (await cur.fetchone())[0]  # type: ignore[index]

    assert first_count == second_count
