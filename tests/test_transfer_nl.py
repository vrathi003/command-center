"""Natural-language transfer line parsing."""

from datetime import date

from finance_common.parsing.expense_parser import try_parse_transfer_line


def test_transfer_from_to_amount() -> None:
    t = try_parse_transfer_line("10000 from hdfc to icici", default_date=date(2026, 1, 15))
    assert t is not None
    assert t.amount_paise == 1_000_000
    assert "hdfc" in (t.fragment_from or "").lower()
    assert "icici" in t.fragment_to.lower()


def test_transfer_sent_to() -> None:
    t = try_parse_transfer_line("sent 2500 to savings account", default_date=date(2026, 1, 15))
    assert t is not None
    assert t.amount_paise == 250_000
    assert "savings" in t.fragment_to.lower()


def test_not_transfer_regular_expense() -> None:
    t = try_parse_transfer_line("500 swiggy", default_date=date(2026, 1, 15))
    assert t is None
