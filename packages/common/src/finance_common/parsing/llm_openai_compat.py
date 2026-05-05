"""OpenAI-compatible HTTP client for local LM Studio only (never OpenAI/Anthropic cloud)."""

from __future__ import annotations

from urllib.parse import urlparse

import httpx
from openai import AsyncOpenAI

from finance_common.config import AppSettings

# LM Studio local server ignores the key but the client requires a non-empty string.
_LM_STUDIO_PLACEHOLDER_KEY = "lm-studio"

# Block known cloud API hosts — traffic must stay local (e.g. LM Studio).
_BLOCKED_HOSTS = frozenset(
    {
        "api.openai.com",
        "api.anthropic.com",
        "openai.azure.com",
    },
)


def _reject_cloud_base_url(base: str) -> None:
    parsed = urlparse(base)
    host = (parsed.hostname or "").lower()
    if not host:
        msg = "LM_STUDIO_URL must be a valid URL with a hostname"
        raise ValueError(msg)
    if host in _BLOCKED_HOSTS:
        msg = (
            f"Refusing to use host {host!r} — use a local LM Studio URL "
            "(e.g. http://127.0.0.1:1234/v1), not OpenAI or Anthropic cloud APIs."
        )
        raise ValueError(msg)
    if host.endswith(".openai.azure.com"):
        msg = "Refusing Azure OpenAI cloud — use local LM Studio only."
        raise ValueError(msg)


def async_openai_for_lm_studio(
    settings: AppSettings,
    *,
    timeout_override: float | None = None,
) -> AsyncOpenAI:
    """Build an AsyncOpenAI-compatible client pointed at LM_STUDIO_URL (local server only).

    Args:
        settings: Application settings (provides URL, model, default timeout).
        timeout_override: When set, overrides ``settings.lm_studio_timeout_seconds`` for
            the HTTP read timeout.  Use this for short-lived calls (e.g. narration
            enrichment) that should fail fast rather than hanging for minutes.
    """
    if not settings.lm_studio_url:
        msg = "LM_STUDIO_URL is not set — required when heuristic PDF parsing fails"
        raise ValueError(msg)
    base = settings.lm_studio_url.rstrip("/")
    _reject_cloud_base_url(base)
    read_s = float(timeout_override if timeout_override is not None else settings.lm_studio_timeout_seconds)
    connect_s = min(60.0, read_s)
    return AsyncOpenAI(
        base_url=base,
        api_key=_LM_STUDIO_PLACEHOLDER_KEY,
        timeout=httpx.Timeout(read_s, connect=connect_s),
    )
