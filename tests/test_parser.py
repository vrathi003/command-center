"""Expense line parser tests."""

from __future__ import annotations

from datetime import date

from finance_common.classification.matcher import ClassificationResult
from finance_common.parsing.expense_parser import parse_expense_line
from finance_common.types import Category, PaymentMode


def test_swiggy_amount() -> None:
    p = parse_expense_line("swiggy 480₹", default_date=date(2026, 3, 24))
    assert p.amount_paise == 48_000
    assert p.category == Category.FOOD_DELIVERY
    assert p.payment_mode == PaymentMode.UPI


def test_rent_bank_transfer() -> None:
    p = parse_expense_line("rent 25000 bank transfer", default_date=date(2026, 3, 24))
    assert p.amount_paise == 2_500_000
    assert p.category == Category.HOUSING_RENT
    assert p.payment_mode == PaymentMode.BANK_TRANSFER


def test_yesterday() -> None:
    p = parse_expense_line("amazon 1200 clothes yesterday", default_date=date(2026, 3, 24))
    assert p.transaction_date == date(2026, 3, 23)
    assert p.amount_paise == 120_000


def test_parse_expense_line_uses_injected_classifier_when_uncategorized() -> None:
    def classify(merchant: str) -> ClassificationResult:
        assert merchant == "custom"
        return ClassificationResult(
            canonical_merchant="Custom Corp",
            merchant_type=None,
            category="Online Shopping",
            matched_rule_id=1,
            match_type="exact",
        )

    p = parse_expense_line("custom 100", default_date=date(2026, 3, 24), classify=classify)
    assert p.category == Category.ONLINE_SHOPPING
    assert p.merchant == "Custom Corp"


def test_parse_expense_line_classify_skipped_when_static_hint_already_matches() -> None:
    """Static keyword hints (e.g. "swiggy") resolve before the classifier is ever consulted."""

    def classify(_merchant: str) -> ClassificationResult:
        raise AssertionError("classify should not be called when a static hint already matched")

    p = parse_expense_line("swiggy 480", default_date=date(2026, 3, 24), classify=classify)
    assert p.category == Category.FOOD_DELIVERY


def test_parse_expense_line_without_classify_keeps_static_behavior() -> None:
    p = parse_expense_line("custom xyz 100", default_date=date(2026, 3, 24))
    assert p.category == Category.OTHER
