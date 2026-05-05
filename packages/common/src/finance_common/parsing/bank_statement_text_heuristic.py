"""Deterministic parsing of bank statement plain text (from PyMuPDF) without any LLM."""

from __future__ import annotations

import re
from datetime import datetime

from finance_common.parsing.transaction_import import extract_merchant_from_narration
from finance_common.types import Category, PaymentMode

# Line must look like: date, narration, amount, optional Dr/Cr
_LINE_ISO = re.compile(
    r"^\s*(\d{4}-\d{2}-\d{2})\s+(.+?)\s+([\d][\d,]*\.?\d{0,2})\s*(Dr|CR|Debit|Credit|DR)?\s*$",
    re.IGNORECASE,
)
_LINE_DMY = re.compile(
    r"^\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s+(.+?)\s+([\d][\d,]*\.?\d{0,2})\s*(Dr|CR|Debit|Credit|DR)?\s*$",
    re.IGNORECASE,
)


def _parse_amount_to_str(raw: str) -> str | None:
    t = raw.strip().replace(",", "").replace("₹", "")
    if not t:
        return None
    try:
        x = float(t)
    except ValueError:
        return None
    if x <= 0:
        return None
    return f"{x:.2f}"


def _dmy_to_iso(s: str) -> str | None:
    s = s.strip()[:10]
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _is_debit_side(side: str | None) -> bool:
    if not side:
        return True
    u = side.strip().upper()
    return u not in ("CR", "CREDIT")


def _infer_category_payment(desc: str, is_debit: bool) -> tuple[Category, PaymentMode]:
    u = desc.upper()
    pm = PaymentMode.OTHER
    if "UPI" in u or "GPAY" in u or "PHONEPE" in u or "PAYTM" in u:
        pm = PaymentMode.UPI
    elif "NEFT" in u or "IMPS" in u or "RTGS" in u:
        pm = PaymentMode.NEFT_IMPS
    elif "ATM" in u or "POS" in u or "DEBIT CARD" in u:
        pm = PaymentMode.HDFC_DC
    elif "CREDIT CARD" in u or " CC " in u:
        pm = PaymentMode.OTHER_CC

    if not is_debit:
        if any(k in u for k in ("SALARY", "PAYROLL", "INTEREST", "DIVIDEND", "CASHBACK")):
            return Category.INCOME, pm
        return Category.TRANSFER, pm

    if any(k in u for k in ("SWIGGY", "ZOMATO", "FOOD")):
        return Category.FOOD_DELIVERY, pm
    if any(k in u for k in ("PETROL", "FUEL", "UBER", "OLA")):
        return Category.TRANSPORT_FUEL, pm
    if "AMAZON" in u or "FLIPKART" in u:
        return Category.OTHER, pm
    if any(k in u for k in ("RENT", "LEASE")):
        return Category.HOUSING_RENT, pm
    return Category.OTHER, pm


def _line_to_row(m: re.Match[str], *, dmy: bool) -> dict[str, str] | None:
    date_raw = m.group(1).strip()
    desc = m.group(2).strip()
    amt_raw = m.group(3).strip()
    groups = m.groups()
    side = groups[3] if len(groups) > 3 else None

    if dmy:
        date_iso = _dmy_to_iso(date_raw)
    else:
        if len(date_raw) < 10:
            return None
        try:
            datetime.fromisoformat(date_raw[:10])
        except ValueError:
            return None
        date_iso = date_raw[:10]
    if not date_iso:
        return None

    amount_s = _parse_amount_to_str(amt_raw)
    if not amount_s:
        return None

    is_debit = _is_debit_side(side)
    cat, pm = _infer_category_payment(desc, is_debit)

    merchant_display = extract_merchant_from_narration(desc) or desc[:200]
    row: dict[str, str] = {
        "date": date_iso,
        "amount": amount_s,
        "category": cat.value,
        "payment_mode": pm.value,
        "merchant": merchant_display[:200],
    }
    if desc != merchant_display or len(desc) > 200:
        row["notes"] = desc[:2000]
    return row


def heuristic_rows_from_statement_text(text: str) -> list[dict[str, str]]:
    """Parse transaction-like lines from raw statement text. No network calls."""
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if len(line) < 12:
            continue
        m = _LINE_ISO.match(line)
        if m:
            r = _line_to_row(m, dmy=False)
            if r:
                rows.append(r)
            continue
        m = _LINE_DMY.match(line)
        if m:
            r = _line_to_row(m, dmy=True)
            if r:
                rows.append(r)
    return rows


def count_transaction_like_lines(text: str) -> int:
    """Count lines that match the same patterns as heuristic parsing (for page scoring)."""
    n = 0
    for line in text.splitlines():
        line = line.strip()
        if len(line) < 12:
            continue
        if _LINE_ISO.match(line) or _LINE_DMY.match(line):
            n += 1
    return n
