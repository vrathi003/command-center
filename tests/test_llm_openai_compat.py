"""LM Studio client must reject OpenAI/Anthropic cloud hosts."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from finance_common.config import AppSettings
from finance_common.parsing.llm_openai_compat import async_openai_for_lm_studio


def _settings_with_lm_url(url: str, *, enabled: bool = True) -> AppSettings:
    """Bypass `.env` so tests control the URL."""
    return AppSettings.model_construct(
        lm_studio_enabled=enabled,
        lm_studio_url=url,
        lm_studio_model="test",
        db_path=Path("/tmp/finance-test.db"),
        app_env="test",
        log_level="INFO",
    )


def test_rejects_when_disabled() -> None:
    s = _settings_with_lm_url("http://127.0.0.1:1234/v1", enabled=False)
    with pytest.raises(ValueError, match="LM_STUDIO_ENABLED=false"):
        async_openai_for_lm_studio(s)


def test_rejects_openai_api_host() -> None:
    s = _settings_with_lm_url("https://api.openai.com/v1")
    with pytest.raises(ValueError, match="Refusing"):
        async_openai_for_lm_studio(s)


def test_rejects_anthropic_host() -> None:
    s = _settings_with_lm_url("https://api.anthropic.com/v1")
    with pytest.raises(ValueError, match="Refusing"):
        async_openai_for_lm_studio(s)


def test_accepts_localhost() -> None:
    s = _settings_with_lm_url("http://127.0.0.1:1234/v1")
    client = async_openai_for_lm_studio(s)
    assert client is not None
    asyncio.run(client.close())
