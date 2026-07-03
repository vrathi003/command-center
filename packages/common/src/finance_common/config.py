"""Application settings loaded from environment (see `.env.example`)."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _expand_path(value: Path) -> Path:
    return Path(value).expanduser().resolve()


class AppSettings(BaseSettings):
    """Shared settings for bot, API, and scripts."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db_path: Path = Field(default=Path("~/finance/finance.db"), alias="DB_PATH")
    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    local_llm_enabled: bool = Field(default=True, alias="LOCAL_LLM_ENABLED")
    local_llm_url: str | None = Field(default=None, alias="LOCAL_LLM_URL")
    local_llm_model: str = Field(default="qwen2.5:1.5b", alias="LOCAL_LLM_MODEL")
    local_llm_timeout_seconds: float = Field(
        default=600.0,
        alias="LOCAL_LLM_TIMEOUT_SECONDS",
        ge=30.0,
        le=3600.0,
    )
    # Shorter timeout used for CSV/XLSX narration enrichment (per batch of ~15 rows).
    # Increase this if your machine is slow. Defaults to 90 s.
    local_llm_narration_timeout_seconds: float = Field(
        default=90.0,
        alias="LOCAL_LLM_NARRATION_TIMEOUT_SECONDS",
        ge=10.0,
        le=600.0,
    )

    @property
    def local_llm_active(self) -> bool:
        """True when local LLM fallback is enabled and a URL is configured."""
        return self.local_llm_enabled and bool(self.local_llm_url)

    @field_validator("local_llm_url", mode="before")
    @classmethod
    def empty_llm_url_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    @field_validator("db_path", mode="before")
    @classmethod
    def expand_db_path(cls, v: str | Path) -> Path:
        return _expand_path(Path(v))
