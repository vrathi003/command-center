"""Financial year utilities for Indian FY (April–March).

All functions are pure and fully testable. The FYYear format is "YYYY-YY",
e.g. "2025-26" means April 1 2025 – March 31 2026.

Month numbering (FY-relative):
  1 = April, 2 = May, ..., 12 = March
"""

from __future__ import annotations

import re
from datetime import date
from typing import NamedTuple

from finance_common.types import FYYear

_FY_PATTERN = re.compile(r"^(\d{4})-(\d{2})$")
_MONTH_LABELS = ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]


class FYParseError(ValueError):
    pass


def _parse(fy: FYYear) -> tuple[int, int]:
    """Return (start_year, end_year) for a FYYear string."""
    m = _FY_PATTERN.match(fy)
    if not m:
        raise FYParseError(f"Invalid FY format '{fy}'. Expected 'YYYY-YY', e.g. '2025-26'.")
    start_year = int(m.group(1))
    end_suffix = int(m.group(2))
    # Validate the suffix: e.g. "2025-26" means end year 2026
    expected_suffix = (start_year + 1) % 100
    if end_suffix != expected_suffix:
        raise FYParseError(
            f"FY year mismatch in '{fy}': suffix '{end_suffix:02d}' doesn't follow {start_year}."
        )
    end_year = start_year + 1
    return start_year, end_year


def fy_start(fy: FYYear) -> date:
    """Return April 1 of the FY start year."""
    start_year, _ = _parse(fy)
    return date(start_year, 4, 1)


def fy_end(fy: FYYear) -> date:
    """Return March 31 of the FY end year."""
    _, end_year = _parse(fy)
    return date(end_year, 3, 31)


def fy_month_start(fy: FYYear, month: int) -> date:
    """Return the first day of a FY month (1=Apr, ..., 12=Mar)."""
    if not 1 <= month <= 12:
        raise ValueError(f"FY month must be 1–12, got {month}")
    start_year, end_year = _parse(fy)
    # Months 1–9 are Apr–Dec (calendar year = FY start year)
    # Months 10–12 are Jan–Mar (calendar year = FY end year)
    if month <= 9:
        cal_month = month + 3  # Apr=4, May=5, ...
        cal_year = start_year
    else:
        cal_month = month - 9  # Jan=1, Feb=2, Mar=3
        cal_year = end_year
    return date(cal_year, cal_month, 1)


def fy_month_end(fy: FYYear, month: int) -> date:
    """Return the last day of a FY month (1=Apr, ..., 12=Mar)."""
    import calendar

    start = fy_month_start(fy, month)
    last_day = calendar.monthrange(start.year, start.month)[1]
    return date(start.year, start.month, last_day)


def fy_month_range(fy: FYYear, month: int) -> tuple[date, date]:
    """Return (first_day, last_day) for a FY month."""
    return fy_month_start(fy, month), fy_month_end(fy, month)


def date_to_fy(d: date) -> FYYear:
    """Return the FYYear that contains the given date."""
    # FY starts April 1. Dates from Jan 1 – Mar 31 belong to the previous FY.
    start_year = d.year if d.month >= 4 else d.year - 1
    end_suffix = (start_year + 1) % 100
    return FYYear(f"{start_year}-{end_suffix:02d}")


def month_label(month: int) -> str:
    """Return the abbreviated month name for a FY month number (1=Apr, 12=Mar)."""
    if not 1 <= month <= 12:
        raise ValueError(f"FY month must be 1–12, got {month}")
    return _MONTH_LABELS[month - 1]


def date_to_fy_month(d: date) -> int:
    """Return the FY month number (1=Apr, ..., 12=Mar) for a date."""
    if d.month >= 4:
        return d.month - 3  # Apr=1, May=2, ..., Dec=9
    else:
        return d.month + 9  # Jan=10, Feb=11, Mar=12


class FYInfo(NamedTuple):
    fy: FYYear
    start: date
    end: date
    months: list[tuple[int, date, date]]  # (month_num, start, end)


def fy_info(fy: FYYear) -> FYInfo:
    """Return complete metadata for a financial year."""
    return FYInfo(
        fy=fy,
        start=fy_start(fy),
        end=fy_end(fy),
        months=[(m, *fy_month_range(fy, m)) for m in range(1, 13)],
    )


def current_fy_from_date(d: date | None = None) -> FYYear:
    """Return the FYYear for today (or the given date)."""
    return date_to_fy(d or date.today())
