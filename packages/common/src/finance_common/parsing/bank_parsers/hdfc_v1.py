"""HDFC Bank credit-card statement parser (v1). Standard line layout.

  15/02/2025 12:02:24 PAYTM UTILITY NOIDA 20.00
  25/02/2025 TATA 1MG HEALTHCARE SOLNEW DELHI 12.73 Cr

Ported from CardQL (CardQL/src/cardql/parsers/banks/hdfc_v1.py).
"""

from __future__ import annotations

import re

from finance_common.parsing.bank_parsers._common import ddmmyyyy_to_iso


def _parse_line(line: str) -> dict[str, str] | None:
    line = line.strip()
    m = re.match(r"^(\d{2}/\d{2}/\d{4})(?:\s+\d{1,2}:\d{2}:\d{2})?\s+(.+)$", line)
    if not m:
        return None
    date_str, rest = m.group(1), m.group(2)
    rest = rest.rstrip()
    is_credit = rest.endswith(" Cr") or rest.endswith("Cr")
    if is_credit:
        rest = rest[:-3].rstrip() if rest.endswith(" Cr") else rest[:-2].rstrip()
    amount_m = re.search(r"[\d,]+\.?\d*\s*$", rest)
    if not amount_m:
        return None
    amount_str = amount_m.group().replace(",", "").strip()
    try:
        float(amount_str)
    except ValueError:
        return None
    description = rest[: amount_m.start()].strip()
    if not description or len(description) > 500:
        return None
    return {
        "date": ddmmyyyy_to_iso(date_str),
        "amount": amount_str,
        "category": "Other",
        "merchant": description,
        "transaction_type": "credit" if is_credit else "debit",
    }


def parse(text: str) -> list[dict[str, str]]:
    """Extract HDFC (v1 layout) credit-card transaction lines from statement text."""
    rows: list[dict[str, str]] = []
    in_section = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if "Domestic Transactions" in line:
            in_section = True
            continue
        if "Reward Points Summary" in line or "International Transactions" in line:
            in_section = False
            continue
        if "Page " in line and " of " in line:
            in_section = True
            continue
        if not in_section or not line:
            continue
        if re.match(r"^\d{2}/\d{2}/\d{4}\s", line):
            row = _parse_line(line)
            if row is not None:
                rows.append(row)
    return rows
