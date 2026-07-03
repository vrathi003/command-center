"""HDFC Bank credit-card statement parser (v2). Newer domestic-transactions table format.

  15/07/2025| 00:00 DESCRIPTION  C 19.80 l          (debit)
  04/08/2025| 08:37 DESCRIPTION +  C 16,099.00 l    (credit / payment)

Ported from CardQL (CardQL/src/cardql/parsers/banks/hdfc_v2.py).
"""

from __future__ import annotations

import re

from finance_common.parsing.bank_parsers._common import ddmmyyyy_to_iso

_LINE_PREFIX = re.compile(r"^(\d{2}/\d{2}/\d{4})\|\s*\d{1,2}:\d{2}\s+(.+)$")
# Do not use a single greedy pattern for both — "CREDIT CARD ... +  C amount l" would
# otherwise match only the trailing " C amount" and drop the "+", mis-classifying as debit.
_CREDIT_TAIL = re.compile(r"^(.+)\s+\+\s+C\s+([\d,]+\.?\d*)\s+l\s*$")
_DEBIT_TAIL = re.compile(r"^(.+)\s+C\s+([\d,]+\.?\d*)\s+l\s*$")


def _parse_line(line: str) -> dict[str, str] | None:
    line = line.strip()
    m0 = _LINE_PREFIX.match(line)
    if not m0:
        return None
    date_str, rest = m0.group(1), m0.group(2)
    m = _CREDIT_TAIL.match(rest)
    is_credit = True
    if not m:
        m = _DEBIT_TAIL.match(rest)
        is_credit = False
    if not m:
        return None
    description, amount_str = m.group(1).strip(), m.group(2).replace(",", "")
    if not description or len(description) > 500:
        return None
    try:
        float(amount_str)
    except ValueError:
        return None
    return {
        "date": ddmmyyyy_to_iso(date_str),
        "amount": amount_str,
        "category": "Other",
        "merchant": description,
        "transaction_type": "credit" if is_credit else "debit",
    }


def parse(text: str) -> list[dict[str, str]]:
    """Extract HDFC (v2 layout) credit-card transaction lines from statement text."""
    rows: list[dict[str, str]] = []
    in_section = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if "Domestic Transactions" in line:
            in_section = True
            continue
        if "Reward Points" in line and "Summary" in line:
            in_section = False
            continue
        if "International Transactions" in line or "GST Summary" in line:
            in_section = False
            continue
        if "Page " in line and " of " in line:
            continue
        if not in_section or not line:
            continue
        row = _parse_line(line)
        if row is not None:
            rows.append(row)
    return rows
