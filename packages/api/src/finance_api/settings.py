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

    # Auth — static API key for dashboard access (empty = disabled)
    app_secret_key: str = Field(default="", alias="APP_SECRET_KEY")

    # Gmail sync
    gmail_credentials_path: Path | None = Field(default=None, alias="GMAIL_CREDENTIALS_PATH")
    gmail_token_path: Path = Field(
        default_factory=lambda: Path("~/finance/gmail_token.json").expanduser().resolve(),
        alias="GMAIL_TOKEN_PATH",
    )
    gmail_sync_lookback_hours: int = Field(default=4, alias="GMAIL_SYNC_LOOKBACK_HOURS")

    @field_validator("backup_dir", mode="before")
    @classmethod
    def expand_backup_dir(cls, v: str | Path | None) -> Path | None:
        if v is None or v == "":
            return None
        return Path(v).expanduser().resolve()

    @field_validator("gmail_credentials_path", mode="before")
    @classmethod
    def expand_gmail_creds(cls, v: str | Path | None) -> Path | None:
        if v is None or v == "":
            return None
        return Path(v).expanduser().resolve()

    @field_validator("gmail_token_path", mode="before")
    @classmethod
    def expand_gmail_token(cls, v: str | Path | None) -> Path:
        if v is None or v == "":
            return Path("~/finance/gmail_token.json").expanduser().resolve()
        return Path(v).expanduser().resolve()
