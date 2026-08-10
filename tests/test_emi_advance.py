"""EMI auto-advance unit tests."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from finance_api.services.amortization import (
    advance_months,
    compute_emi_advance,
    emis_due_count,
    _overdue_emi_count,
)
from finance_common.repositories.debts import DebtRow


def _debt(**kwargs: object) -> DebtRow:
    defaults = dict(
        id=1,
        name="Car Loan",
        lender="HDFC",
        type="Car Loan",
        original_amount_paise=1_000_000_00,
        current_balance_paise=900_000_00,
        emi_paise=20_000_00,
        rate_percent=9.0,
        start_date="2025-01-03",
        next_emi_date="2026-07-03",
        status="active",
        tenure_months=60,
        first_emi_date="2025-01-03",
        full_emi_start_date=None,
    )
    defaults.update(kwargs)
    return DebtRow(**defaults)  # type: ignore[arg-type]


def test_emis_due_count_on_due_day() -> None:
    first = date(2025, 1, 3)
    assert emis_due_count(first, date(2025, 1, 3)) == 1
    assert emis_due_count(first, date(2025, 1, 2)) == 0


def test_emis_due_count_after_due_day() -> None:
    first = date(2025, 1, 3)
    assert emis_due_count(first, date(2026, 7, 6)) == 19


def test_overdue_emi_count() -> None:
    due = date(2026, 7, 3)
    assert _overdue_emi_count(due, date(2026, 7, 2)) == 0
    assert _overdue_emi_count(due, date(2026, 7, 3)) == 1
    assert _overdue_emi_count(due, date(2026, 7, 6)) == 1
    assert _overdue_emi_count(due, date(2026, 8, 3)) == 2


@patch("finance_api.services.amortization.date")
def test_compute_emi_advance_advances_past_next_emi(mock_date: object) -> None:
    mock_date.today.return_value = date(2026, 7, 6)  # type: ignore[attr-defined]
    mock_date.side_effect = lambda *a, **k: date(*a, **k)  # type: ignore[attr-defined]
    mock_date.fromisoformat = date.fromisoformat  # type: ignore[attr-defined]

    row = _debt(next_emi_date="2026-07-03")
    result = compute_emi_advance(row)
    assert result is not None
    new_bal, new_next, status = result
    assert new_next == advance_months(date(2025, 1, 3), 19).isoformat()
    assert new_next == "2026-08-03"
    assert status == "active"
    assert new_bal < row.current_balance_paise


@patch("finance_api.services.amortization.date")
def test_compute_emi_advance_skips_future_next_emi(mock_date: object) -> None:
    mock_date.today.return_value = date(2026, 7, 2)  # type: ignore[attr-defined]
    mock_date.side_effect = lambda *a, **k: date(*a, **k)  # type: ignore[attr-defined]
    mock_date.fromisoformat = date.fromisoformat  # type: ignore[attr-defined]

    row = _debt(next_emi_date="2026-07-03")
    assert compute_emi_advance(row) is None


@patch("finance_api.services.amortization.date")
def test_compute_emi_advance_next_emi_only_fallback(mock_date: object) -> None:
    mock_date.today.return_value = date(2026, 7, 6)  # type: ignore[attr-defined]
    mock_date.side_effect = lambda *a, **k: date(*a, **k)  # type: ignore[attr-defined]
    mock_date.fromisoformat = date.fromisoformat  # type: ignore[attr-defined]

    row = _debt(
        first_emi_date=None,
        start_date=None,
        next_emi_date="2026-07-03",
        current_balance_paise=500_000_00,
        emi_paise=25_000_00,
        original_amount_paise=None,
        rate_percent=None,
        tenure_months=None,
    )
    result = compute_emi_advance(row)
    assert result == (475_000_00, "2026-08-03", "active")
