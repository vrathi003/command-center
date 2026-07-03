"""ICICI Bank credit-card statement parser (v1). Serial-numbered transaction lines.

  15/01/2026 12702848045 REPOVIVE, INC. COLLEGE PARK US 18 940.19
  29/01/2026 12776056934 BBPS Payment received 0 1,160.54 CR

Ported from CardQL (CardQL/src/cardql/parsers/banks/icici_v1.py).
"""

from __future__ import annotations

import re

from finance_common.parsing.bank_parsers._common import ddmmyyyy_to_iso


def _parse_line(line: str) -> dict[str, str] | None:
    line = line.strip()
    if not re.match(r"^\d{2}/\d{2}/\d{4}\s+\d+", line) or len(line.split()) < 4:
        return None
    tokens = line.split()
    date_str = tokens[0]
    is_credit = tokens[-1] == "CR"
    if is_credit:
        amount_str = tokens[-2].replace(",", "")
        desc_tokens = tokens[2:-2]
    else:
        amount_str = tokens[-1].replace(",", "")
        desc_tokens = tokens[2:-1]
    try:
        float(amount_str)
    except ValueError:
        return None
    description = " ".join(desc_tokens) if desc_tokens else ""
    if not description:
        return None
    return {
        "date": ddmmyyyy_to_iso(date_str),
        "amount": amount_str,
        "category": "Other",
        "merchant": description,
        "transaction_type": "credit" if is_credit else "debit",
    }


def parse(text: str) -> list[dict[str, str]]:
    """Extract ICICI credit-card transaction lines from statement text."""
    rows: list[dict[str, str]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or "Statement period" in line or "Date SerNo" in line or "Amount (in" in line:
            continue
        if line.startswith("3747") or line.startswith("Credit Limit"):
            continue
        if re.match(r"^\d{2}/\d{2}/\d{4}\s+\d{10,}", line):
            row = _parse_line(line)
            if row is not None:
                rows.append(row)
    return rows
