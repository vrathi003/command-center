"""SBI Card credit-card statement parser (v1). D/C/M suffix amounts.

  18 May 25 NETFLIX MUMBAI MAH 199.00 D
  02 Jun 25 PAYMENT RECEIVED ... 5,744.34 C

Ported from CardQL (CardQL/src/cardql/parsers/banks/sbi_v1.py).
"""

from __future__ import annotations

import re

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}  # fmt: skip

_TXN_LINE_RE = re.compile(
    r"^\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{2}\s+"
    r".+\s+[\d,]+\.\d+\s+[DCM]$",
    re.IGNORECASE,
)


def _ddmonyy_to_iso(d: str) -> str:
    m = re.match(r"^(\d{1,2})\s+(\w{3})\s+(\d{2})$", d.strip(), re.IGNORECASE)
    if not m:
        return d
    try:
        day = int(m.group(1))
        mon = _MONTHS.get(m.group(2).lower())
        year = int(m.group(3))
        year = year + 2000 if year < 50 else year + 1900
        if mon is None:
            return d
        return f"{year:04d}-{mon:02d}-{day:02d}"
    except (ValueError, IndexError):
        return d


def _parse_line(line: str) -> dict[str, str] | None:
    line = line.strip()
    m = re.match(r"^(\d{1,2}\s+\w{3}\s+\d{2})\s+(.+)$", line, re.IGNORECASE)
    if not m or len(m.group(2).split()) < 2:
        return None
    date_str, rest = m.group(1), m.group(2)
    tokens = rest.split()
    if tokens[-1] not in ("D", "C", "M"):
        return None
    is_credit = tokens[-1] == "C"
    amount_str = tokens[-2].replace(",", "")
    try:
        float(amount_str)
    except ValueError:
        return None
    description = " ".join(tokens[:-2]) if len(tokens) > 2 else ""
    if not description:
        return None
    return {
        "date": _ddmonyy_to_iso(date_str),
        "amount": amount_str,
        "category": "Other",
        "merchant": description,
        "transaction_type": "credit" if is_credit else "debit",
    }


def parse(text: str) -> list[dict[str, str]]:
    """Extract SBI Card credit-card transaction lines from statement text.

    SBI statement text order is not always sequential (payment credits often appear
    above the transactions header; some debits appear below trailing summary blocks),
    so lines are matched by shape anywhere in the text rather than a section marker,
    and duplicate lines are dropped.
    """
    rows: list[dict[str, str]] = []
    seen_lines: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or not _TXN_LINE_RE.match(line):
            continue
        if line in seen_lines:
            continue
        seen_lines.add(line)
        row = _parse_line(line)
        if row is not None:
            rows.append(row)
    rows.sort(key=lambda r: (r["date"], r.get("merchant", "")))
    return rows
