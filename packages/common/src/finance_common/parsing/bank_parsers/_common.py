"""Shared helpers for per-bank statement text parsers."""

from __future__ import annotations

import re

MONTH_NAMES_3 = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def ddmmyyyy_to_iso(d: str) -> str:
    """'15/02/2025' -> '2025-02-15'. Returns the input unchanged if unparseable."""
    parts = d.split("/")
    if len(parts) != 3:
        return d
    try:
        day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
        return f"{year:04d}-{month:02d}-{day:02d}"
    except (ValueError, IndexError):
        return d


def dd_mon_yyyy_to_iso(s: str) -> str | None:
    """'15 Aug, 2025' -> '2025-08-15'."""
    m = re.match(r"(\d{1,2})\s+(\w{3}),?\s*(\d{4})", s.strip())
    if not m:
        return None
    try:
        day = int(m.group(1))
        month_str = m.group(2)
        year = int(m.group(3))
        if month_str not in MONTH_NAMES_3:
            return None
        month = MONTH_NAMES_3.index(month_str) + 1
        return f"{year:04d}-{month:02d}-{day:02d}"
    except (ValueError, IndexError):
        return None
