"""Expense line parser tests."""

from __future__ import annotations

from datetime import date

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
