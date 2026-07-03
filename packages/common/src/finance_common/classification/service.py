"""Async entry point for merchant classification — fetches rules, delegates to the matcher."""

from __future__ import annotations

import aiosqlite

from finance_common.classification.matcher import ClassificationResult, match_merchant
from finance_common.repositories import merchant_rules as merchant_rules_repo


async def classify_merchant(
    conn: aiosqlite.Connection, raw_merchant: str | None
) -> ClassificationResult:
    """One-off classification (fetches rules fresh). Batch callers should instead fetch
    rules once via ``merchant_rules_repo.list_active_rules_for_matching`` and call
    ``match_merchant`` directly per row to avoid a DB round-trip per transaction."""
    rules = await merchant_rules_repo.list_active_rules_for_matching(conn)
    return match_merchant(raw_merchant, rules)
