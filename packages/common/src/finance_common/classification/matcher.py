"""Pure merchant-string matching against merchant_rules — no I/O.

Callers that already hold a fetched rule list (one DB round-trip per batch, not per
row) should call ``match_merchant`` directly; see ``classification.service`` for the
async convenience wrapper used by single-shot callers.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from finance_common.repositories.merchant_rules import MerchantRuleRow


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    canonical_merchant: str | None
    merchant_type: str | None
    category: str | None
    matched_rule_id: int | None
    match_type: str | None  # 'exact' | 'contains' | None (no match)


ClassifyFn = Callable[[str], ClassificationResult]

_NO_MATCH = ClassificationResult(
    canonical_merchant=None,
    merchant_type=None,
    category=None,
    matched_rule_id=None,
    match_type=None,
)


def match_merchant(raw_merchant: str | None, rules: list[MerchantRuleRow]) -> ClassificationResult:
    """Exact match wins over contains; longest match_value wins among contains matches;
    ties broken by priority desc, then id asc (earliest-created rule wins)."""
    if not raw_merchant:
        return _NO_MATCH
    lower = raw_merchant.strip().lower()
    if not lower:
        return _NO_MATCH

    exact = [r for r in rules if r.match_type == "exact" and r.match_value == lower]
    if exact:
        best = max(exact, key=lambda r: (r.priority, -r.id))
        return _to_result(best, "exact")

    contains = [r for r in rules if r.match_type == "contains" and r.match_value in lower]
    if contains:
        best = max(contains, key=lambda r: (len(r.match_value), r.priority, -r.id))
        return _to_result(best, "contains")

    return _NO_MATCH


def _to_result(rule: MerchantRuleRow, match_type: str) -> ClassificationResult:
    return ClassificationResult(
        canonical_merchant=rule.canonical_merchant,
        merchant_type=rule.merchant_type,
        category=rule.category,
        matched_rule_id=rule.id,
        match_type=match_type,
    )
