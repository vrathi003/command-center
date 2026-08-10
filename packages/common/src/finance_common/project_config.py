"""Typed project configuration stored in SQLite settings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import aiosqlite

from finance_common.repositories.settings_repo import get_value, set_value

LedgerEngine = Literal["legacy", "double_entry"]

KEY_DISCORD_ENABLED = "project_config.discord.enabled"
KEY_DISCORD_ALERTS_ENABLED = "project_config.discord.alerts.enabled"
KEY_ALERTS_IN_APP_ENABLED = "project_config.alerts.in_app.enabled"
KEY_LEDGER_ENGINE = "project_config.ledger.engine"
KEY_INTAKE_AUTO_POST_MIN_CONFIDENCE = "project_config.intake.auto_post.min_confidence"
KEY_INTAKE_DUPLICATE_DATE_WINDOW_DAYS = "project_config.intake.duplicate.date_window_days"


@dataclass
class ProjectConfig:
    discord_enabled: bool = False
    discord_alerts_enabled: bool = False
    alerts_in_app_enabled: bool = True
    ledger_engine: LedgerEngine = "double_entry"
    intake_auto_post_min_confidence: float = 0.85
    intake_duplicate_date_window_days: int = 1


def _parse_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    return raw.lower() == "true"


def _parse_float(raw: str | None, default: float) -> float:
    if raw is None:
        return default
    return float(raw)


def _parse_int(raw: str | None, default: int) -> int:
    if raw is None:
        return default
    return int(raw)


def _parse_ledger_engine(raw: str | None, default: LedgerEngine) -> LedgerEngine:
    if raw is None:
        return default
    if raw in ("legacy", "double_entry"):
        return raw  # type: ignore[return-value]
    return default


async def load_project_config(conn: aiosqlite.Connection) -> ProjectConfig:
    defaults = ProjectConfig()
    return ProjectConfig(
        discord_enabled=_parse_bool(
            await get_value(conn, KEY_DISCORD_ENABLED), defaults.discord_enabled
        ),
        discord_alerts_enabled=_parse_bool(
            await get_value(conn, KEY_DISCORD_ALERTS_ENABLED),
            defaults.discord_alerts_enabled,
        ),
        alerts_in_app_enabled=_parse_bool(
            await get_value(conn, KEY_ALERTS_IN_APP_ENABLED),
            defaults.alerts_in_app_enabled,
        ),
        ledger_engine=_parse_ledger_engine(
            await get_value(conn, KEY_LEDGER_ENGINE), defaults.ledger_engine
        ),
        intake_auto_post_min_confidence=_parse_float(
            await get_value(conn, KEY_INTAKE_AUTO_POST_MIN_CONFIDENCE),
            defaults.intake_auto_post_min_confidence,
        ),
        intake_duplicate_date_window_days=_parse_int(
            await get_value(conn, KEY_INTAKE_DUPLICATE_DATE_WINDOW_DAYS),
            defaults.intake_duplicate_date_window_days,
        ),
    )


def _bool_str(value: bool) -> str:
    return "true" if value else "false"


async def save_project_config(conn: aiosqlite.Connection, cfg: ProjectConfig) -> None:
    await set_value(conn, KEY_DISCORD_ENABLED, _bool_str(cfg.discord_enabled))
    await set_value(conn, KEY_DISCORD_ALERTS_ENABLED, _bool_str(cfg.discord_alerts_enabled))
    await set_value(conn, KEY_ALERTS_IN_APP_ENABLED, _bool_str(cfg.alerts_in_app_enabled))
    await set_value(conn, KEY_LEDGER_ENGINE, cfg.ledger_engine)
    await set_value(
        conn,
        KEY_INTAKE_AUTO_POST_MIN_CONFIDENCE,
        str(cfg.intake_auto_post_min_confidence),
    )
    await set_value(
        conn,
        KEY_INTAKE_DUPLICATE_DATE_WINDOW_DAYS,
        str(cfg.intake_duplicate_date_window_days),
    )
