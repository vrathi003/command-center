"""Tests for Indian FY helpers."""

from __future__ import annotations

from datetime import date

import pytest

from finance_common.fy import (
    FYParseError,
    date_to_fy,
    date_to_fy_month,
    fy_end,
    fy_month_start,
    fy_start,
)
from finance_common.types import FYYear


def test_fy_parse_round_trip() -> None:
    fy = FYYear("2025-26")
    assert fy_start(fy) == date(2025, 4, 1)
    assert fy_end(fy) == date(2026, 3, 31)


def test_invalid_fy_suffix() -> None:
    with pytest.raises(FYParseError):
        _ = fy_start(FYYear("2025-27"))


def test_date_to_fy() -> None:
    assert date_to_fy(date(2026, 3, 24)) == FYYear("2025-26")
    assert date_to_fy(date(2026, 4, 1)) == FYYear("2026-27")


def test_fy_month_numbering() -> None:
    fy = FYYear("2025-26")
    assert fy_month_start(fy, 1) == date(2025, 4, 1)
    assert fy_month_start(fy, 12) == date(2026, 3, 1)
    assert date_to_fy_month(date(2025, 4, 15)) == 1
    assert date_to_fy_month(date(2026, 3, 1)) == 12
