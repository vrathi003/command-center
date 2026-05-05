"""Heuristic expense line parser (regex + keyword maps).

LLM-backed parsing can wrap/replace this later; the contract stays `ParsedExpense`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

from finance_common.parsing.account_mentions import TRANSFER_PATTERNS, extract_account_fragment
from finance_common.types import Category, Paise, PaymentMode, rupees_to_paise

_AMOUNT_RE = re.compile(
    r"(?:₹|rs\.?|inr)?\s*(\d[\d,]*(?:\.\d+)?)\s*(?:₹|rs\.?)?",
    re.IGNORECASE,
)

# Longer phrases first so "bank transfer" wins over "bank"
_PAYMENT_HINTS: list[tuple[str, PaymentMode]] = [
    ("hdfc cc", PaymentMode.HDFC_CC),
    ("hdfc credit", PaymentMode.HDFC_CC),
    ("sbi cc", PaymentMode.SBI_CC),
    ("icici cc", PaymentMode.ICICI_CC),
    ("axis cc", PaymentMode.AXIS_CC),
    ("credit card", PaymentMode.OTHER_CC),
    ("bank transfer", PaymentMode.BANK_TRANSFER),
    ("neft", PaymentMode.NEFT_IMPS),
    ("imps", PaymentMode.NEFT_IMPS),
    ("upi", PaymentMode.UPI),
    ("cash", PaymentMode.CASH),
    ("emi", PaymentMode.EMI),
]

_CATEGORY_HINTS: list[tuple[str, Category]] = [
    ("bigbasket", Category.GROCERIES),
    ("groceries", Category.GROCERIES),
    ("grocery", Category.GROCERIES),
    ("swiggy", Category.FOOD_DELIVERY),
    ("zomato", Category.FOOD_DELIVERY),
    ("food delivery", Category.FOOD_DELIVERY),
    ("lunch", Category.DINING_OUT),
    ("dinner", Category.DINING_OUT),
    ("petrol", Category.TRANSPORT_FUEL),
    ("fuel", Category.TRANSPORT_FUEL),
    ("uber", Category.TRANSPORT_FUEL),
    ("ola", Category.TRANSPORT_FUEL),
    ("rent", Category.HOUSING_RENT),
    ("doctor", Category.HEALTH_MEDICAL),
    ("medical", Category.HEALTH_MEDICAL),
    ("health", Category.HEALTH_MEDICAL),
    ("amazon", Category.OTHER),
    ("clothes", Category.CLOTHING),
    ("clothing", Category.CLOTHING),
    ("emi", Category.EMI_LOAN),
    ("loan", Category.EMI_LOAN),
    ("car", Category.EMI_LOAN),
    ("invest", Category.INVESTMENTS),
    ("sip", Category.INVESTMENTS),
]


class ExpenseParseError(ValueError):
    """Raised when a line cannot be interpreted as an expense."""


@dataclass(frozen=True, slots=True)
class ParsedTransferLine:
    """Natural-language transfer between accounts (Discord / quick-add)."""

    amount_paise: Paise
    fragment_from: str | None
    fragment_to: str
    transaction_date: date
    notes: str | None


# Explicit: "5000 from HDFC to ICICI" (amount first)
_AMT_FROM_TO_RE = re.compile(
    r"(?:₹|rs\.?|inr)?\s*(\d[\d,.]+)\s+from\s+(.+?)\s+to\s+(.+)$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_rupees_token(s: str) -> float | None:
    raw = s.replace(",", "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def try_parse_transfer_line(
    text: str, *, default_date: date | None = None
) -> ParsedTransferLine | None:
    """If the line matches a transfer phrase, return structured fields; else None."""
    raw = text.strip()
    if not raw:
        return None
    base = default_date or date.today()
    lower = raw.lower()
    tx_date = _resolve_date(lower, base)

    m = _AMT_FROM_TO_RE.search(raw.strip())
    if m:
        rupees = _parse_rupees_token(m.group(1))
        if rupees is None or rupees <= 0 or rupees > 1e12:
            return None
        fr = m.group(2).strip().strip(" \t,.;:")
        to = m.group(3).strip().strip(" \t,.;:")
        if not to:
            return None
        return ParsedTransferLine(
            amount_paise=rupees_to_paise(rupees),
            fragment_from=fr if fr else None,
            fragment_to=to,
            transaction_date=tx_date,
            notes=raw,
        )

    # paid … account … amount (groups: account name, amount)
    paid_pat = TRANSFER_PATTERNS[-1]
    m = paid_pat.search(raw)
    if m:
        rupees = _parse_rupees_token(m.group(2))
        if rupees is None or rupees <= 0 or rupees > 1e12:
            return None
        to_frag = m.group(1).strip().strip(" \t,.;:")
        if not to_frag:
            return None
        from_hint = extract_account_fragment(raw)
        return ParsedTransferLine(
            amount_paise=rupees_to_paise(rupees),
            fragment_from=from_hint,
            fragment_to=to_frag,
            transaction_date=tx_date,
            notes=raw,
        )

    for pat in TRANSFER_PATTERNS[:-1]:
        m = pat.search(raw)
        if not m:
            continue
        rupees = _parse_rupees_token(m.group(1))
        if rupees is None or rupees <= 0 or rupees > 1e12:
            return None
        to_frag = m.group(2).strip().strip(" \t,.;:")
        if not to_frag:
            return None
        from_hint = extract_account_fragment(raw)
        return ParsedTransferLine(
            amount_paise=rupees_to_paise(rupees),
            fragment_from=from_hint,
            fragment_to=to_frag,
            transaction_date=tx_date,
            notes=raw,
        )

    return None


@dataclass(frozen=True, slots=True)
class ParsedExpense:
    amount_paise: Paise
    category: Category
    merchant: str | None
    payment_mode: PaymentMode
    transaction_date: date
    notes: str | None


def _first_amount_rupees(text: str) -> tuple[float, str] | None:
    """Return (rupees, text with amount span blanked) or None."""
    m = _AMOUNT_RE.search(text)
    if not m:
        return None
    raw = m.group(1).replace(",", "")
    try:
        value = float(raw)
    except ValueError:
        return None
    blanked = text[: m.start()] + " " + text[m.end() :]
    return value, blanked


def _resolve_date(text_lower: str, default: date) -> date:
    if "yesterday" in text_lower:
        return default - timedelta(days=1)
    if "today" in text_lower:
        return default
    return default


def _payment_mode(text_lower: str) -> PaymentMode:
    for hint, mode in _PAYMENT_HINTS:
        if hint in text_lower:
            return mode
    return PaymentMode.UPI


def _category(text_lower: str) -> Category:
    for hint, cat in _CATEGORY_HINTS:
        if hint in text_lower:
            return cat
    return Category.OTHER


def _merchant_guess(cleaned: str) -> str | None:
    """Pick a short merchant label from leftover tokens."""
    tokens = [t for t in re.split(r"\s+", cleaned.strip()) if t]
    stop = {
        "today",
        "yesterday",
        "upi",
        "cc",
        "bank",
        "transfer",
        "the",
        "a",
        "an",
        "and",
        "for",
        "rs",
        "inr",
    }
    candidates = [t for t in tokens if t.lower() not in stop and not t.replace(",", "").isdigit()]
    if not candidates:
        return None
    # Prefer capitalised / brand-like first token
    return candidates[0][:80]


def parse_expense_line(text: str, *, default_date: date | None = None) -> ParsedExpense:
    """Parse a single natural-language expense line into structured fields."""
    raw = text.strip()
    if not raw:
        raise ExpenseParseError("Empty expense text.")

    base = default_date or date.today()
    lower = raw.lower()
    tx_date = _resolve_date(lower, base)

    got = _first_amount_rupees(raw)
    if got is None:
        raise ExpenseParseError(f"Could not find an amount in: {raw!r}")
    rupees, remainder = got
    if rupees <= 0 or rupees > 1e12:
        raise ExpenseParseError(f"Amount out of range: {rupees}")

    remainder_lower = remainder.lower()
    category = _category(remainder_lower)
    if "clothes" in remainder_lower or "clothing" in remainder_lower:
        category = Category.CLOTHING
    if (
        "amazon" in remainder_lower or "flipkart" in remainder_lower
    ) and category == Category.OTHER:
        category = Category.OTHER

    pay = _payment_mode(remainder_lower)
    merchant = _merchant_guess(remainder)
    paise = rupees_to_paise(rupees)

    notes: str | None = remainder.strip() or None
    return ParsedExpense(
        amount_paise=paise,
        category=category,
        merchant=merchant,
        payment_mode=pay,
        transaction_date=tx_date,
        notes=notes,
    )
