from pathlib import Path

import aiosqlite
import pytest

from finance_common.db import ensure_database
from finance_common.project_config import (
    ProjectConfig,
    is_legacy_cutover,
    load_project_config,
    mark_legacy_cutover,
    save_project_config,
    uses_ledger_books,
)


@pytest.mark.asyncio
async def test_defaults_discord_off(tmp_path: Path) -> None:
    db = tmp_path / "c.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        cfg = await load_project_config(conn)
    assert cfg.discord_enabled is False
    assert cfg.ledger_engine == "double_entry"
    assert cfg.recon_match_date_window_days == 2


@pytest.mark.asyncio
async def test_legacy_cutover_defaults_to_false_and_can_be_marked(tmp_path: Path) -> None:
    db = tmp_path / "c.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        assert await is_legacy_cutover(conn) is False
        assert await uses_ledger_books(conn) is True
        cfg = await load_project_config(conn)
        assert cfg.legacy_cutover_at is None
        assert cfg.legacy_archive is False

        await mark_legacy_cutover(conn, "2026-08-10T12:00:00+00:00")

        assert await is_legacy_cutover(conn) is True
        assert await uses_ledger_books(conn) is True
        cfg = await load_project_config(conn)
    assert cfg.legacy_cutover_at == "2026-08-10T12:00:00+00:00"
    assert cfg.legacy_archive is True


@pytest.mark.asyncio
async def test_uses_ledger_books_follows_engine_not_cutover(tmp_path: Path) -> None:
    db = tmp_path / "c.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        await save_project_config(conn, ProjectConfig(ledger_engine="legacy"))
        assert await uses_ledger_books(conn) is False
        assert await is_legacy_cutover(conn) is False

        await mark_legacy_cutover(conn, "2026-08-10T12:00:00+00:00")
        assert await is_legacy_cutover(conn) is True
        assert await uses_ledger_books(conn) is False

        await save_project_config(conn, ProjectConfig(ledger_engine="double_entry"))
        assert await uses_ledger_books(conn) is True


@pytest.mark.asyncio
async def test_roundtrip(tmp_path: Path) -> None:
    db = tmp_path / "c.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        await save_project_config(
            conn,
            ProjectConfig(discord_enabled=True, ledger_engine="legacy"),
        )
        cfg = await load_project_config(conn)
    assert cfg.discord_enabled is True
    assert cfg.ledger_engine == "legacy"


@pytest.mark.asyncio
async def test_recon_match_date_window_roundtrips(tmp_path: Path) -> None:
    db = tmp_path / "c.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        await save_project_config(conn, ProjectConfig(recon_match_date_window_days=4))
        cfg = await load_project_config(conn)

    assert cfg.recon_match_date_window_days == 4
