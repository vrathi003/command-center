import pytest
from pathlib import Path
import aiosqlite
from finance_common.db import ensure_database
from finance_common.project_config import load_project_config, save_project_config, ProjectConfig

@pytest.mark.asyncio
async def test_defaults_discord_off(tmp_path: Path) -> None:
    db = tmp_path / "c.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        cfg = await load_project_config(conn)
    assert cfg.discord_enabled is False
    assert cfg.ledger_engine == "double_entry"

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
