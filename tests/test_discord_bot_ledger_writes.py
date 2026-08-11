"""Discord product ledger writes under ledger_engine=double_entry."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import aiosqlite
import pytest

from finance_common.db import ensure_database
from finance_common.ledger import product_writes as pw
from finance_common.ledger import service as ledger_service
from finance_common.project_config import ProjectConfig, save_project_config


async def _seed_cash(conn: aiosqlite.Connection) -> dict[str, int]:
    await conn.executemany(
        "INSERT INTO accounts (name, type, account_class) VALUES (?, ?, ?)",
        [
            ("Bank", "savings", "asset_cash"),
            ("Bank 2", "savings", "asset_cash"),
        ],
    )
    await conn.commit()
    cur = await conn.execute(
        "SELECT id, name FROM accounts WHERE name IN ('Bank', 'Bank 2')"
    )
    return {str(name): int(aid) for aid, name in await cur.fetchall()}


@pytest.mark.asyncio
async def test_post_manual_requires_account(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        with pytest.raises(pw.ProductWriteError, match="Include an account"):
            await pw.post_manual(
                conn,
                tx_date=date(2026, 8, 11),
                amount_paise=100,
                category="Food",
                merchant="Cafe",
                transaction_type="debit",
                account_id=None,
                notes="x",
            )


@pytest.mark.asyncio
async def test_post_manual_and_void_without_legacy_rows(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _seed_cash(conn)
        tid = await pw.post_manual(
            conn,
            tx_date=date(2026, 8, 11),
            amount_paise=12_500,
            category="Food",
            merchant="Cafe",
            transaction_type="debit",
            account_id=ids["Bank"],
            notes="lunch",
            external_key="discord:msg-1",
        )
        legacy = await (
            await conn.execute("SELECT COUNT(*) FROM transactions")
        ).fetchone()
        assert int(legacy[0]) == 0
        tx = await ledger_service.get_transaction(conn, tid)
        assert tx.source == "discord"
        assert tx.status == "posted"

        await pw.void_posted(conn, tid)
        assert (await ledger_service.get_transaction(conn, tid)).status == "void"


@pytest.mark.asyncio
async def test_post_transfer_and_latest_by_source(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        ids = await _seed_cash(conn)
        tid = await pw.post_transfer(
            conn,
            tx_date=date(2026, 8, 11),
            amount_paise=5_000,
            from_account_id=ids["Bank"],
            to_account_id=ids["Bank 2"],
            notes="move",
        )
        assert await pw.latest_posted_id_by_source(conn, source="discord") == tid
        await pw.void_posted(conn, tid)
        assert await pw.latest_posted_id_by_source(conn, source="discord") is None


@pytest.mark.asyncio
async def test_legacy_engine_flag_still_loads(tmp_path: Path) -> None:
    """Sanity: product helpers are only for DE; legacy config remains settable."""
    db = tmp_path / "t.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        await save_project_config(conn, ProjectConfig(ledger_engine="legacy"))
        from finance_common.project_config import uses_ledger_books

        assert await uses_ledger_books(conn) is False
