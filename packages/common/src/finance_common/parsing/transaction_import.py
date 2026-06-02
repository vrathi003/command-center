"""Parse rows from CSV/Excel exports into transaction fields."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime

from finance_common.parsing.account_mentions import narration_suggests_bank_transfer
from finance_common.parsing.import_column_mapping import (
    build_canonical_import_row,
    normalize_header_key,
    resolve_column_role,
    score_header_row,
)
from finance_common.types import Category, PaymentMode, rupees_to_paise

# Re-export for callers/tests that import from this module.
__all__ = [
    "normalize_header_key",
    "resolve_column_role",
    "detect_header_row",
    "canonical_row_for_import",
    "trim_trailer_rows",
    "parse_import_row",
    "iter_csv_dict_rows",
]


@dataclass(frozen=True, slots=True)
class ParsedImportRow:
    tx_date: date
    amount_paise: int
    category: str
    merchant: str | None
    payment_mode: str
    account: str | None
    notes: str | None
    transaction_type: str  # "debit", "credit", or "transfer"


# Keywords that indicate a trailer/summary row rather than a real transaction.
_TRAILER_KEYWORDS = frozenset(
    {"total", "totals", "statement", "generated", "disclaimer", "page", "opening", "closing"}
)


def detect_header_row(rows: list[list[str]], *, max_scan: int = 20) -> int | None:
    """Return 0-based index of the most likely header row, or None if not found.

    Scans at most *max_scan* rows.  A candidate must have >= 2 known header keys
    and at least one must be a date-family key.  The candidate with the highest
    score wins; ties broken by earliest row.
    """
    best_idx: int | None = None
    best_score = 0
    for i, row in enumerate(rows[:max_scan]):
        score, has_date = score_header_row(row)
        if score >= 2 and has_date and score > best_score:
            best_score = score
            best_idx = i
    return best_idx


def trim_trailer_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Remove trailing non-data rows (totals, disclaimers, rows with empty dates)."""
    if not rows:
        return rows
    end = len(rows)
    while end > 0:
        row = rows[end - 1]
        # Try to find a date value via any known date header key.
        date_val = ""
        for k, v in row.items():
            nk = normalize_header_key(k)
            if resolve_column_role(nk) == "date":
                date_val = (v or "").strip()
                break
        if not date_val:
            end -= 1
            continue
        # Check if the date cell contains a trailer keyword instead of a real date.
        lower = date_val.lower()
        if any(kw in lower for kw in _TRAILER_KEYWORDS):
            end -= 1
            continue
        break
    return rows[:end]


def canonical_row_for_import(raw: dict[str, str]) -> dict[str, str]:
    """Map export row to canonical fields; fills amount from debit/credit columns."""
    return build_canonical_import_row(raw)


def parse_transaction_date(s: str) -> date:
    t = s.strip()
    if not t:
        raise ValueError("empty date")
    try:
        return date.fromisoformat(t[:10])
    except ValueError:
        pass
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(t[:10], fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date format: {s!r}")


def parse_amount_rupees(s: str) -> int:
    """Return amount in paise; expense amounts are stored as positive paise."""
    t = s.strip()
    if not t:
        raise ValueError("empty amount")
    t = re.sub(r"[₹,\s]", "", t)
    if not t:
        raise ValueError("empty amount after strip")
    try:
        val = float(t)
    except ValueError as e:
        raise ValueError(f"invalid number: {s!r}") from e
    paise = rupees_to_paise(abs(val))
    if int(paise) <= 0:
        raise ValueError("amount must be non-zero")
    return int(paise)


# Merchant keyword → category hints for auto-categorization during import.
_MERCHANT_CATEGORY_HINTS: list[tuple[str, Category]] = [
    ("bigbasket", Category.GROCERIES),
    ("blinkit", Category.GROCERIES),
    ("zepto", Category.GROCERIES),
    ("dmart", Category.GROCERIES),
    ("groceries", Category.GROCERIES),
    ("grocery", Category.GROCERIES),
    ("supermarket", Category.GROCERIES),
    ("swiggy", Category.FOOD_DELIVERY),
    ("zomato", Category.FOOD_DELIVERY),
    ("food delivery", Category.FOOD_DELIVERY),
    ("dunzo", Category.FOOD_DELIVERY),
    ("lunch", Category.DINING_OUT),
    ("dinner", Category.DINING_OUT),
    ("restaurant", Category.DINING_OUT),
    ("cafe", Category.DINING_OUT),
    ("starbucks", Category.DINING_OUT),
    ("petrol", Category.TRANSPORT_FUEL),
    ("fuel", Category.TRANSPORT_FUEL),
    ("uber", Category.TRANSPORT_FUEL),
    ("ola", Category.TRANSPORT_FUEL),
    ("rapido", Category.TRANSPORT_FUEL),
    ("irctc", Category.TRAVEL),
    ("makemytrip", Category.TRAVEL),
    ("cleartrip", Category.TRAVEL),
    ("rent", Category.HOUSING_RENT),
    ("electricity", Category.UTILITIES),
    ("water bill", Category.UTILITIES),
    ("gas bill", Category.UTILITIES),
    ("broadband", Category.UTILITIES),
    ("jio", Category.UTILITIES),
    ("airtel", Category.UTILITIES),
    ("doctor", Category.HEALTH_MEDICAL),
    ("medical", Category.HEALTH_MEDICAL),
    ("pharmacy", Category.HEALTH_MEDICAL),
    ("hospital", Category.HEALTH_MEDICAL),
    ("apollo", Category.HEALTH_MEDICAL),
    ("netflix", Category.SUBSCRIPTIONS),
    ("spotify", Category.SUBSCRIPTIONS),
    ("amazon prime", Category.SUBSCRIPTIONS),
    ("hotstar", Category.SUBSCRIPTIONS),
    ("youtube", Category.SUBSCRIPTIONS),
    ("clothes", Category.CLOTHING),
    ("clothing", Category.CLOTHING),
    ("myntra", Category.CLOTHING),
    ("emi", Category.EMI_LOAN),
    ("loan", Category.EMI_LOAN),
    ("creditsaison", Category.EMI_LOAN),
    ("invest", Category.INVESTMENTS),
    ("sip", Category.INVESTMENTS),
    ("mutual fund", Category.INVESTMENTS),
    ("zerodha", Category.INVESTMENTS),
    ("groww", Category.INVESTMENTS),
    ("insurance", Category.INSURANCE),
    ("lic", Category.INSURANCE),
]


# UPI with 6–22 digit reference (NPCI-style) then payee: UPI/DR/102786697305/APPLE ME/HDFC/...
_UPI_PAYEE_AFTER_REF = re.compile(r"UPI/(?:DR|CR)/\d{6,22}/\s*([^/]+)", re.IGNORECASE)
# UPI without numeric ref in some exports: UPI/DR/Zomato Ltd/YESBANK/...
_UPI_PAYEE_NO_REF = re.compile(r"UPI/(?:DR|CR)/([^/]+)/", re.IGNORECASE)


def extract_merchant_from_narration(text: str) -> str:
    """Short counterparty from Indian bank/UPI narration (HDFC, etc.).

    Picks the payee segment after ``UPI/DR/<ref>/`` or ``UPI/CR/<ref>/``, or after ``UPI/DR/``
    when the first segment is not a numeric reference. Falls back to the full string (trimmed).
    """
    t = (text or "").strip()
    if not t:
        return ""
    m = _UPI_PAYEE_AFTER_REF.search(t)
    if m:
        return _clean_merchant_segment(m.group(1))
    m = _UPI_PAYEE_NO_REF.search(t)
    if m:
        slug = m.group(1).strip()
        if not slug.isdigit():
            return _clean_merchant_segment(slug)
    if "/" not in t and len(t) <= 64:
        return t[:200]
    return t[:200]


def _clean_merchant_segment(s: str) -> str:
    s = re.sub(r"\s+", " ", s.strip())
    return s[:200] if s else ""


def categorize_from_merchant(merchant: str | None) -> str | None:
    """Return a category string if the merchant matches a known keyword, else None."""
    if not merchant:
        return None
    lower = merchant.lower()
    for keyword, cat in _MERCHANT_CATEGORY_HINTS:
        if keyword in lower:
            return cat.value
    return None


def parse_import_row(canon: dict[str, str]) -> ParsedImportRow:
    if "date" not in canon or "amount" not in canon or "category" not in canon:
        raise ValueError("required columns: date, amount, category")
    tx_date = parse_transaction_date(canon["date"])
    amount_paise = parse_amount_rupees(canon["amount"])
    cat = Category.from_string(canon["category"])
    pm_raw = canon.get("payment_mode") or "Other"
    pm = PaymentMode.from_string(pm_raw)
    merchant = canon.get("merchant") or None
    notes = canon.get("notes") or None
    if merchant:
        slim = extract_merchant_from_narration(merchant)
        if slim and slim != merchant.strip():
            if not notes:
                notes = merchant
            merchant = slim
    # Auto-categorize from merchant when category defaults to "Other".
    if cat == Category.OTHER and merchant:
        auto_cat = categorize_from_merchant(merchant)
        if auto_cat:
            cat = Category.from_string(auto_cat)
    # Auto-detect payment mode from narration (merchant may be shortened; notes hold original).
    if pm == PaymentMode.OTHER:
        probe = " ".join(
            x for x in (notes, merchant, canon.get("merchant")) if x
        ).lower()
        if "upi" in probe or "upi/" in probe:
            pm = PaymentMode.UPI
        elif "neft" in probe or "imps" in probe:
            pm = PaymentMode.NEFT_IMPS
        elif "atm" in probe:
            pm = PaymentMode.CASH
    account = canon.get("account") or None
    tx_type = canon.get("transaction_type") or "debit"
    narration_probe = " ".join(
        x for x in (notes, merchant, canon.get("merchant")) if x
    )
    if narration_suggests_bank_transfer(narration_probe):
        cat = Category.TRANSFER
        tx_type = "transfer"
    return ParsedImportRow(
        tx_date=tx_date,
        amount_paise=amount_paise,
        category=cat.value,
        merchant=merchant,
        payment_mode=pm.value,
        account=account,
        notes=notes,
        transaction_type=tx_type,
    )


def iter_csv_dict_rows(content: bytes) -> list[dict[str, str]]:
    """Decode CSV (UTF-8 with optional BOM) and return list of row dicts (string values)."""
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return []
    rows: list[dict[str, str]] = []
    for raw in reader:
        row = {k: (v if v is not None else "") for k, v in raw.items()}
        if not any(str(v).strip() for v in row.values()):
            continue
        rows.append(row)
    return rows
