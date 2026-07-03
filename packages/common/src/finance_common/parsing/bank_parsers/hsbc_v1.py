"""HSBC Bank credit-card statement parser (v1). DDMMM-style dates (no separators).

Statement text has no fixed column layout, so the amount is found by scanning forward
from each date match for the smallest plausible rupee amount in a sane range.

Ported from CardQL (CardQL/src/cardql/parsers/banks/hsbc_v1.py).
"""

from __future__ import annotations

import re

_MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}  # fmt: skip

_STOP_MARKERS = [
    "TOTAL PURCHASE OUTSTANDING",
    "TOTAL CASH OUTSTANDING",
    "NET OUTSTANDING BALANCE",
    "PURCHASES & INSTALLMENTS",
    "Interest Rate applicable",
]


def _ddmmm_to_iso(date_str: str, year: int) -> str:
    m = re.match(r"^(\d{2})([A-Z]{3})$", date_str.upper())
    if not m:
        return date_str
    day, mon = m.group(1), m.group(2)
    month = _MONTHS.get(mon)
    if month is None:
        return date_str
    return f"{year:04d}-{month:02d}-{int(day):02d}"


def _extract_year(text: str) -> int | None:
    m = re.search(r"\b(20\d{2})\s+To\s+\d{1,2}\s+[A-Z]{3}\s+(20\d{2})", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r"\b(20\d{2})\b", text)
    return int(m.group(1)) if m else None


def _amount_value(m: re.Match[str]) -> float:
    try:
        return float(m.group().replace(",", ""))
    except (ValueError, AttributeError):
        return 0.0


def parse(text: str) -> list[dict[str, str]]:
    """Extract HSBC credit-card transaction lines from statement text."""
    year = _extract_year(text) or 2026
    rows: list[dict[str, str]] = []
    month_pattern = "|".join(_MONTHS.keys())
    pattern = re.compile(r"(\d{2})(" + month_pattern + r")", re.IGNORECASE)

    pos = 0
    start_marker = re.search(
        r"(?:OPENING BALANCE|PURCHASES\s*&\s*INSTALLMENTS)", text, re.IGNORECASE
    )
    if start_marker:
        pos = start_marker.end()

    for match in pattern.finditer(text, pos):
        date_str = (match.group(1) + match.group(2).upper())[:5]
        if len(date_str) != 5 or date_str[2:5] not in _MONTHS:
            continue
        segment_start = match.start()
        next_match = pattern.search(text, match.end() + 1)
        segment_end = next_match.start() if next_match else len(text)
        for stop in _STOP_MARKERS:
            idx = text.find(stop, segment_start)
            if 0 <= idx < segment_end:
                segment_end = idx
        after_date = text[segment_start:segment_end][5:].strip()

        found: list[re.Match[str]] = [
            m
            for m in (
                re.search(re.escape(g.group(1)), after_date)
                for g in re.finditer(r"(?=(\d{1,2},\d{3}\.\d{2}))", after_date)
            )
            if m is not None
        ]
        if not found:
            found = list(re.finditer(r"[\d,]+\.\d{2}\b", after_date))
        if not found:
            continue

        values = [(_amount_value(m), m) for m in found if 1 <= _amount_value(m) <= 500_000]
        if not values:
            continue
        _, best_match = min(values, key=lambda x: x[0])
        amount_str = best_match.group().replace(",", "")
        try:
            amount_val = float(amount_str)
        except ValueError:
            continue
        if amount_val <= 0:
            continue
        desc = after_date[: best_match.start()].strip()
        if not desc or len(desc) > 500:
            continue
        rows.append(
            {
                "date": _ddmmm_to_iso(date_str, year),
                "amount": amount_str,
                "category": "Other",
                "merchant": desc,
                "transaction_type": "debit",
            }
        )
    return rows
