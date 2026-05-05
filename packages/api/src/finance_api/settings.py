"""API-specific settings."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator

from finance_common.config import AppSettings


class ApiSettings(AppSettings):
    api_host: str = Field(default="127.0.0.1", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    scheduler_timezone: str = Field(default="Asia/Kolkata", alias="SCHEDULER_TIMEZONE")
    jobs_enabled: bool = Field(default=True, alias="JOBS_ENABLED")
    backup_dir: Path | None = Field(default=None, alias="BACKUP_DIR")
    discord_bot_token: str | None = Field(default=None, alias="DISCORD_BOT_TOKEN")
    discord_user_id: str | None = Field(default=None, alias="DISCORD_USER_ID")

    @field_validator("backup_dir", mode="before")
    @classmethod
    def expand_backup_dir(cls, v: str | Path | None) -> Path | None:
        if v is None or v == "":
            return None
        return Path(v).expanduser().resolve()
