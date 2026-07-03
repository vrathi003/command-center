"""OpenAI-compatible HTTP client for local LLM inference (LM Studio, Ollama, etc.)."""

from __future__ import annotations

from urllib.parse import urlparse

import httpx
from openai import AsyncOpenAI

from finance_common.config import AppSettings

# Local servers ignore the API key but the client requires a non-empty string.
_LOCAL_PLACEHOLDER_KEY = "local-llm"

# Block known cloud API hosts — traffic must stay local.
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
        msg = "LOCAL_LLM_URL must be a valid URL with a hostname"
        raise ValueError(msg)
    if host in _BLOCKED_HOSTS:
        msg = (
            f"Refusing to use host {host!r} — use a local inference URL "
            "(e.g. http://localhost:11434/v1 for Ollama or http://127.0.0.1:1234/v1 "
            "for LM Studio), not OpenAI or Anthropic cloud APIs."
        )
        raise ValueError(msg)
    if host.endswith(".openai.azure.com"):
        msg = "Refusing Azure OpenAI cloud — use a local inference server only."
        raise ValueError(msg)


def async_openai_for_local_llm(
    settings: AppSettings,
    *,
    timeout_override: float | None = None,
) -> AsyncOpenAI:
    """Build an AsyncOpenAI-compatible client pointed at LOCAL_LLM_URL.

    Works with Ollama (http://localhost:11434/v1), LM Studio
    (http://127.0.0.1:1234/v1), or any other OpenAI-compatible local server.

    Args:
        settings: Application settings (provides URL, model, default timeout).
        timeout_override: When set, overrides ``settings.local_llm_timeout_seconds``
            for the HTTP read timeout.  Use for short-lived calls (e.g. narration
            enrichment) that should fail fast rather than hanging for minutes.
    """
    if not settings.local_llm_enabled:
        msg = "Local LLM is disabled (LOCAL_LLM_ENABLED=false)"
        raise ValueError(msg)
    if not settings.local_llm_url:
        msg = "LOCAL_LLM_URL is not set — required when heuristic PDF parsing fails"
        raise ValueError(msg)
    base = settings.local_llm_url.rstrip("/")
    _reject_cloud_base_url(base)
    read_s = float(
        timeout_override if timeout_override is not None else settings.local_llm_timeout_seconds
    )
    connect_s = min(60.0, read_s)
    return AsyncOpenAI(
        base_url=base,
        api_key=_LOCAL_PLACEHOLDER_KEY,
        timeout=httpx.Timeout(read_s, connect=connect_s),
    )


# Backwards-compat alias — remove after all callers updated.
async_openai_for_lm_studio = async_openai_for_local_llm
