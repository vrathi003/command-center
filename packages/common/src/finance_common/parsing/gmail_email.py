"""Parse Indian bank transaction alerts and merchant receipts from Gmail email bodies."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from email.utils import parsedate_to_datetime

from finance_common.parsing.transaction_import import categorize_from_merchant

# ── Amount extraction ────────────────────────────────────────────────────────

_AMOUNT_RE = re.compile(
    r"(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d{1,2})?)",
    re.IGNORECASE,
)


def _parse_amount_paise(text: str) -> int | None:
    m = _AMOUNT_RE.search(text)
    if not m:
        return None
    try:
        return int(round(float(m.group(1).replace(",", "")) * 100))
    except ValueError:
        return None


# ── Date extraction from email header ────────────────────────────────────────

def _parse_email_date(date_header: str | None) -> date | None:
    if not date_header:
        return None
    try:
        return parsedate_to_datetime(date_header).date()
    except Exception:
        return None


# ── Sender domain routing ─────────────────────────────────────────────────────

_BANK_DOMAINS = {
    "hdfcbank.com",
    "icicibank.com",
    "sbi.co.in",
    "axisbank.com",
    "kotak.com",
    "indusind.com",
    "idfcfirstbank.com",
    "federalbank.co.in",
    "yesbank.in",
    "pnb.co.in",
    "bankofbaroda.in",
    "canarabank.in",
    "sc.com",
    "standardchartered.co.in",
    "rblbank.com",
    "idbibank.com",
}

_MERCHANT_SENDER_TO_NAME: dict[str, str] = {
    "swiggy.in": "Swiggy",
    "zomato.com": "Zomato",
    "amazon.in": "Amazon",
    "flipkart.com": "Flipkart",
    "myntra.com": "Myntra",
    "paytm.com": "Paytm",
    "phonepe.com": "PhonePe",
    "makemytrip.com": "MakeMyTrip",
    "irctc.co.in": "IRCTC",
    "bookmyshow.com": "BookMyShow",
    "nykaa.com": "Nykaa",
    "meesho.com": "Meesho",
    "bigbasket.com": "BigBasket",
    "blinkit.com": "Blinkit",
    "zepto.co": "Zepto",
    "dunzo.com": "Dunzo",
    "urbancompany.com": "UrbanCompany",
    "airtel.in": "Airtel",
    "jio.com": "Jio",
    "razorpay.com": "Razorpay",
    "instamojo.com": "Instamojo",
}


def _sender_domain(sender: str) -> str:
    """Extract domain from email address like 'HDFC Bank <alerts@hdfcbank.com>'."""
    m = re.search(r"@([\w.-]+)", sender.lower())
    return m.group(1) if m else ""


def _is_bank_sender(domain: str) -> bool:
    return any(domain == bd or domain.endswith("." + bd) for bd in _BANK_DOMAINS)


def _merchant_from_sender(domain: str) -> str | None:
    for md, name in _MERCHANT_SENDER_TO_NAME.items():
        if domain == md or domain.endswith("." + md):
            return name
    return None


# ── CC last-four extraction ───────────────────────────────────────────────────

# Matches: "ending 1234", "ending in 1234", "XX1234", "x-1234", "card **1234"
_CC_LAST_FOUR_RE = re.compile(
    r"(?:ending\s+(?:in\s+)?|xx+[-\s]?|card\s+\*+\s*)(\d{4})\b",
    re.IGNORECASE,
)


def _extract_cc_last_four(text: str) -> str | None:
    m = _CC_LAST_FOUR_RE.search(text)
    return m.group(1) if m else None


# ── Bank alert parsing ────────────────────────────────────────────────────────

_DEBIT_KEYWORDS = re.compile(
    r"\b(?:debited|deducted|withdrawn|spent|paid|charged|purchase|payment made)\b",
    re.IGNORECASE,
)
_CREDIT_KEYWORDS = re.compile(
    r"\b(?:credited|received|deposited|refunded|cashback|credit)\b",
    re.IGNORECASE,
)

# Extract merchant from UPI narration like "UPI/DR/12345/MerchantName/BANK/ref"
_UPI_NARRATION_RE = re.compile(
    r"(?:UPI|IMPS)/(?:DR|CR)/\d+/([^/]+)/",
    re.IGNORECASE,
)
# "to MERCHANT" / "for MERCHANT" / "at MERCHANT"
_MERCHANT_RE = re.compile(
    r"\b(?:to|for|at|towards)\s+([A-Za-z0-9][A-Za-z0-9 &\-_.]{1,40}?)(?:\s+(?:via|using|with|on|at|ref|utr|a\/c|account)|[.,\n]|$)",
    re.IGNORECASE,
)


def _extract_merchant_from_body(body: str) -> str | None:
    m = _UPI_NARRATION_RE.search(body)
    if m:
        name = m.group(1).strip()
        if len(name) > 1:
            return name
    m = _MERCHANT_RE.search(body)
    if m:
        name = m.group(1).strip().rstrip(".,")
        if len(name) > 1:
            return name
    return None


def parse_bank_alert(
    subject: str,
    sender: str,
    body: str,
    email_date: date | None,
) -> ParsedEmailTransaction | None:
    """Parse Indian bank transaction alert email."""
    combined = f"{subject} {body}"
    amount_paise = _parse_amount_paise(combined)
    if not amount_paise or amount_paise <= 0:
        return None

    debit_score = len(_DEBIT_KEYWORDS.findall(combined))
    credit_score = len(_CREDIT_KEYWORDS.findall(combined))
    if debit_score == 0 and credit_score == 0:
        return None

    tx_type = "credit" if credit_score > debit_score else "debit"
    merchant = _extract_merchant_from_body(combined)
    category = categorize_from_merchant(merchant) or ("Income" if tx_type == "credit" else "Other")
    payment_mode = _detect_payment_mode(combined)
    cc_last_four = _extract_cc_last_four(combined)

    return ParsedEmailTransaction(
        tx_date=email_date or date.today(),
        amount_paise=amount_paise,
        transaction_type=tx_type,
        merchant=merchant,
        category=category,
        payment_mode=payment_mode,
        raw_snippet=(combined[:500]).strip(),
        cc_last_four=cc_last_four,
    )


def _detect_payment_mode(text: str) -> str:
    t = text.upper()
    if "UPI" in t:
        return "UPI"
    if "NEFT" in t or "RTGS" in t or "IMPS" in t:
        return "NEFT/RTGS"
    if "ATM" in t:
        return "ATM"
    if "CREDIT CARD" in t or "CC" in t:
        return "Credit Card"
    if "DEBIT CARD" in t:
        return "Debit Card"
    if "NET BANKING" in t or "INTERNET BANKING" in t:
        return "Net Banking"
    return "Other"


# ── Merchant receipt parsing ──────────────────────────────────────────────────

_ORDER_TOTAL_RE = re.compile(
    r"(?:order\s+total|total\s+amount|amount\s+paid|you\s+paid|total\s+bill)[:\s]+(?:₹|Rs\.?|INR)?\s*([\d,]+(?:\.\d{1,2})?)",
    re.IGNORECASE,
)


def parse_payment_receipt(
    subject: str,
    merchant_name: str,
    body: str,
    email_date: date | None,
) -> ParsedEmailTransaction | None:
    """Parse e-commerce / merchant receipt email."""
    combined = f"{subject} {body}"

    # Try order total pattern first, then generic amount
    m = _ORDER_TOTAL_RE.search(combined)
    if m:
        try:
            amount_paise = int(round(float(m.group(1).replace(",", "")) * 100))
        except ValueError:
            amount_paise = 0
    else:
        amount_paise = _parse_amount_paise(combined) or 0

    if amount_paise <= 0:
        return None

    category = categorize_from_merchant(merchant_name) or "Shopping"
    return ParsedEmailTransaction(
        tx_date=email_date or date.today(),
        amount_paise=amount_paise,
        transaction_type="debit",
        merchant=merchant_name,
        category=category,
        payment_mode="UPI",
        raw_snippet=combined[:500].strip(),
    )


# ── Public entry point ────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class ParsedEmailTransaction:
    tx_date: date
    amount_paise: int
    transaction_type: str  # 'debit' | 'credit'
    merchant: str | None
    category: str
    payment_mode: str
    raw_snippet: str
    cc_last_four: str | None = None  # set for CC transaction alerts


def classify_and_parse(
    subject: str,
    sender: str,
    body: str,
    date_header: str | None = None,
) -> ParsedEmailTransaction | None:
    """
    Route to the correct parser based on sender domain.
    Returns None if the email does not appear to be a financial transaction.
    """
    domain = _sender_domain(sender)
    email_date = _parse_email_date(date_header)

    if _is_bank_sender(domain):
        return parse_bank_alert(subject, sender, body, email_date)

    merchant_name = _merchant_from_sender(domain)
    if merchant_name:
        return parse_payment_receipt(subject, merchant_name, body, email_date)

    # Fallback: check subject/body for financial signals
    combined = f"{subject} {body}"
    has_amount = bool(_AMOUNT_RE.search(combined))
    has_tx_signal = bool(_DEBIT_KEYWORDS.search(combined) or _CREDIT_KEYWORDS.search(combined))
    has_order_signal = bool(re.search(
        r"\b(?:order\s+(?:confirmed|placed|total)|payment\s+(?:successful|confirmed|received))\b",
        combined, re.IGNORECASE,
    ))
    if has_amount and (has_tx_signal or has_order_signal):
        return parse_bank_alert(subject, sender, body, email_date)

    return None
