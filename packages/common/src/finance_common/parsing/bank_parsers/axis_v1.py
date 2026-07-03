"""Axis Bank credit-card statement parser (v1).

Columnar DD/MM/YYYY lines with trailing Dr|Cr amounts, e.g.:
  14/02/2025 ZOMATO RESTAURANTS 547.59 Dr
  17/02/2025 BBPS PAYMENT RECEIVED - ... 13.00 Cr

Ported from CardQL (CardQL/src/cardql/parsers/banks/axis_v1.py).
"""

from __future__ import annotations

import re

from finance_common.parsing.bank_parsers._common import ddmmyyyy_to_iso

_TWO_WORD_CATEGORIES = {
    ("DEPT", "STORES"),
    ("AUTO", "SERVICES"),
    ("HOME", "FURNISHING"),
    ("FOOD", "PRODUCTS"),
}


def _parse_line(line: str) -> dict[str, str] | None:
    line = line.strip()
    date_match = re.match(r"^(\d{2}/\d{2}/\d{4})\s+(.+)$", line)
    if not date_match:
        return None
    date_str, rest = date_match.group(1), date_match.group(2)
    tokens = rest.split()
    if len(tokens) < 3 or tokens[-1] not in ("Dr", "Cr"):
        return None
    sign = tokens[-1]
    amount_str = tokens[-2].replace(",", "")
    try:
        float(amount_str)
    except ValueError:
        return None
    if len(tokens) >= 4 and (tokens[-4], tokens[-3]) in _TWO_WORD_CATEGORIES:
        category_tag = f"{tokens[-4]} {tokens[-3]}"
        desc_tokens = tokens[:-4]
    else:
        category_tag = tokens[-3]
        desc_tokens = tokens[:-3]
    description = " ".join(desc_tokens) if desc_tokens else ""
    if not description:
        return None
    return {
        "date": ddmmyyyy_to_iso(date_str),
        "amount": amount_str,
        "category": "Other",
        "merchant": description,
        "transaction_type": "credit" if sign == "Cr" else "debit",
        "notes": f"Axis category: {category_tag}",
    }


def parse(text: str) -> list[dict[str, str]]:
    """Extract Axis credit-card transaction lines from statement text."""
    rows: list[dict[str, str]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or "End of Statement" in line or line.startswith("DATE TRANSACTION DETAILS"):
            continue
        if re.match(r"^\d{2}/\d{2}/\d{4}\s*-\s*\d{2}/\d{2}/\d{4}", line):
            continue
        row = _parse_line(line)
        if row is not None:
            rows.append(row)
    return rows
