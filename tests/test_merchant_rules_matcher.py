"""Pure merchant-matching logic tests (no DB)."""

from __future__ import annotations

from finance_common.classification.matcher import match_merchant
from finance_common.repositories.merchant_rules import MerchantRuleRow


def _rule(
    id_: int,
    match_type: str,
    match_value: str,
    *,
    canonical: str = "Merchant",
    category: str = "Other",
    priority: int = 0,
) -> MerchantRuleRow:
    return MerchantRuleRow(
        id=id_,
        match_type=match_type,
        match_value=match_value,
        canonical_merchant=canonical,
        merchant_type=None,
        category=category,
        source="user",
        confidence=1.0,
        priority=priority,
        is_active=True,
        created_at="2026-01-01",
        updated_at="2026-01-01",
        last_matched_at=None,
    )


def test_no_match_on_empty_input() -> None:
    result = match_merchant(None, [_rule(1, "contains", "swiggy")])
    assert result.category is None
    assert result.matched_rule_id is None
    assert result.match_type is None

    result2 = match_merchant("", [_rule(1, "contains", "swiggy")])
    assert result2.matched_rule_id is None


def test_no_match_when_no_rules_apply() -> None:
    result = match_merchant("random merchant xyz", [_rule(1, "contains", "swiggy")])
    assert result.matched_rule_id is None


def test_exact_match() -> None:
    rules = [_rule(1, "exact", "swiggy", canonical="Swiggy", category="Food Delivery")]
    result = match_merchant("Swiggy", rules)
    assert result.match_type == "exact"
    assert result.canonical_merchant == "Swiggy"
    assert result.category == "Food Delivery"
    assert result.matched_rule_id == 1


def test_exact_is_case_insensitive() -> None:
    rules = [_rule(1, "exact", "swiggy")]
    assert match_merchant("SWIGGY", rules).matched_rule_id == 1


def test_contains_match() -> None:
    rules = [_rule(1, "contains", "swiggy", canonical="Swiggy", category="Food Delivery")]
    result = match_merchant("UPI-SWIGGY-swiggy@ybl-4829", rules)
    assert result.match_type == "contains"
    assert result.matched_rule_id == 1


def test_exact_beats_contains() -> None:
    rules = [
        _rule(1, "contains", "swiggy", canonical="Swiggy (generic)"),
        _rule(2, "exact", "swiggy instamart", canonical="Swiggy Instamart"),
    ]
    result = match_merchant("swiggy instamart", rules)
    assert result.match_type == "exact"
    assert result.matched_rule_id == 2


def test_longest_contains_wins() -> None:
    rules = [
        _rule(1, "contains", "swiggy", canonical="Swiggy"),
        _rule(2, "contains", "swiggy instamart", canonical="Swiggy Instamart"),
    ]
    result = match_merchant("swiggy instamart order", rules)
    assert result.matched_rule_id == 2


def test_tie_broken_by_priority_then_earliest_id() -> None:
    rules = [
        _rule(2, "contains", "swiggy", priority=0),
        _rule(1, "contains", "swiggy", priority=0),
    ]
    result = match_merchant("swiggy", rules)
    assert result.matched_rule_id == 1  # earliest id wins when priority ties

    rules_with_priority = [
        _rule(1, "contains", "swiggy", priority=0),
        _rule(2, "contains", "swiggy", priority=5),
    ]
    result2 = match_merchant("swiggy", rules_with_priority)
    assert result2.matched_rule_id == 2  # higher priority wins


def test_inactive_rules_excluded_by_caller() -> None:
    """match_merchant trusts its input list — filtering inactive rules is the repo's job."""
    rules = [_rule(1, "exact", "swiggy")]
    assert match_merchant("swiggy", rules).matched_rule_id == 1
    assert match_merchant("swiggy", []).matched_rule_id is None
