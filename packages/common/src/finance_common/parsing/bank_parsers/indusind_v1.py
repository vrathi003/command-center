"""IndusInd Bank credit-card statement parser (v1). Standard statement layout.

  17/01/2026 DINING OUTLET GURGAON IN RESTAURANTS 21 1,043.00 DR

Ported from CardQL (CardQL/src/cardql/parsers/banks/indusind_v1.py).
"""

from __future__ import annotations

import re

from finance_common.parsing.bank_parsers._common import ddmmyyyy_to_iso


def _parse_line(line: str) -> dict[str, str] | None:
    line = line.strip()
    m = re.match(r"^(\d{2}/\d{2}/\d{4})\s+(.+)$", line)
    if not m or len(m.group(2).split()) < 3:
        return None
    date_str, rest = m.group(1), m.group(2)
    tokens = rest.split()
    if tokens[-1].upper() not in ("DR", "CR"):
        return None
    is_credit = tokens[-1].upper() == "CR"
    amount_str = tokens[-2].replace(",", "")
    try:
        float(amount_str)
    except ValueError:
        return None
    category_tag = tokens[-3] if len(tokens) >= 3 else None
    description = " ".join(tokens[:-3]) if tokens[:-3] else ""
    if not description:
        return None
    row = {
        "date": ddmmyyyy_to_iso(date_str),
        "amount": amount_str,
        "category": "Other",
        "merchant": description,
        "transaction_type": "credit" if is_credit else "debit",
    }
    if category_tag:
        row["notes"] = f"IndusInd category: {category_tag}"
    return row


def parse(text: str) -> list[dict[str, str]]:
    """Extract IndusInd credit-card transaction lines from statement text."""
    rows: list[dict[str, str]] = []
    in_section = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if "Purchases & Cash Transactions" in line or "Date Transaction Details" in line:
            in_section = True
            continue
        if line.startswith("Total ") and re.search(r"\d+\s+[\d,]+\.\d+", line):
            in_section = False
            continue
        if not in_section or not line:
            continue
        if re.match(r"^\d{2}/\d{2}/\d{4}\s+.+\s+DR$", line) or re.match(
            r"^\d{2}/\d{2}/\d{4}\s+.+\s+CR$", line
        ):
            row = _parse_line(line)
            if row is not None:
                rows.append(row)
    return rows
