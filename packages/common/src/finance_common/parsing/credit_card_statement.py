"""Parse credit card statement text (PDF extract) and tabular exports for review/import."""

from __future__ import annotations

import json
import re
from typing import Any

from finance_common.classification.matcher import ClassifyFn
from finance_common.parsing.bank_statement_text_heuristic import heuristic_rows_from_statement_text
from finance_common.parsing.transaction_import import (
    canonical_row_for_import,
    parse_amount_rupees,
    parse_import_row,
    parse_transaction_date,
)
from finance_common.types import PaymentMode

MAX_LINE_ITEMS = 500
MAX_EXTRACTION_PREVIEW = 32_000

# ── CC line-item taxonomy ────────────────────────────────────────────────────

_RE_PAYMENT = re.compile(
    r"payment\s+(?:received|thank\s*you|credited|made|processed)"
    r"|payment\s*/\s*thank\s*you"
    r"|online\s+payment"
    r"|(?:amount|amt)\s+paid"
    r"|refund\s+by\s+merchant"
    r"|(?:bank\s+)?transfer\s+(?:received|credit)",
    re.I,
)

_RE_INTEREST = re.compile(
    r"interest\s+(?:charged|levied|on\s+revolving|charges?)"
    r"|finance\s+charges?"
    r"|interest\s+charges?"
    r"|gst\s+on\s+(?:interest|finance|charges)"
    r"|deferred\s+interest"
    r"|revolving\s+(?:interest|charges?)",
    re.I,
)

_RE_FEE = re.compile(
    r"late\s+(?:payment\s+)?(?:charges?|fees?|fee)"
    r"|annual\s+(?:membership\s+)?(?:fee|charges?)"
    r"|membership\s+fees?"
    r"|over[-\s]?limit\s+(?:fee|charges?)"
    r"|overlimit"
    r"|cash\s+advance\s+(?:fee|charges?)"
    r"|forex\s+(?:markup\s+)?(?:fee|charges?)"
    r"|foreign\s+(?:transaction|currency)\s+(?:fee|charges?)"
    r"|(?:processing|convenience|service)\s+(?:fee|charges?)"
    r"|gst\s+on\s+(?:fee|annual)"
    r"|(?:card|account)\s+(?:penalty|charges?)"
    r"|mis[-\s]?payment"
    r"|penalty",
    re.I,
)

_RE_CASHBACK = re.compile(
    r"cashback\s+(?:credit|redemption|earned)"
    r"|reward\s+(?:point\s+)?redemption"
    r"|reward\s+(?:credit|earned|adjustment)"
    r"|loyalty\s+(?:points?\s+)?(?:credit|redemption)",
    re.I,
)

_RE_REFUND = re.compile(
    r"(?:merchant\s+)?refund"
    r"|(?:credit|debit)\s+(?:note|adjustment|reversal)"
    r"|reversal",
    re.I,
)


def _classify_cc_description(description: str) -> dict[str, object]:
    """
    Returns {'skip': bool, 'transaction_type': str, 'category': str}.

    skip=True means the line is a payment/receipt that shouldn't be imported
    as a spending transaction (e.g. "Payment Received").
    """
    desc = description.strip()
    if _RE_PAYMENT.search(desc):
        return {"skip": True, "transaction_type": "credit", "category": "Other"}
    if _RE_INTEREST.search(desc):
        return {"skip": False, "transaction_type": "debit", "category": "Bank Charges"}
    if _RE_FEE.search(desc):
        return {"skip": False, "transaction_type": "debit", "category": "Bank Charges"}
    if _RE_CASHBACK.search(desc):
        return {"skip": False, "transaction_type": "credit", "category": "Income"}
    if _RE_REFUND.search(desc):
        return {"skip": False, "transaction_type": "credit", "category": "Other"}
    return {"skip": False, "transaction_type": "debit", "category": None}


# Indian CC / common English labels (amounts in ₹)
_RUPEE_NUM = r"([\d][\d,]*(?:\.\d{1,2})?)"

def _pat(label: str, pattern: str) -> tuple[re.Pattern[str], str]:
    return (re.compile(pattern, re.I), label)


_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    _pat("total_due_paise", rf"Total\s+(?:Amount\s+)?Due[^\d₹]*(?:₹\s*)?{_RUPEE_NUM}"),
    _pat("min_due_paise", rf"Minimum\s+(?:Amount\s+)?Due[^\d₹]*(?:₹\s*)?{_RUPEE_NUM}"),
    _pat("credit_limit_paise", rf"(?:Total\s+)?Credit\s+Limit[^\d₹]*(?:₹\s*)?{_RUPEE_NUM}"),
    _pat("available_credit_paise", rf"Available\s+(?:Credit|Limit)[^\d₹]*(?:₹\s*)?{_RUPEE_NUM}"),
    _pat(
        "closing_balance_paise",
        rf"(?:Closing|Outstanding)\s+Balance[^\d₹]*(?:₹\s*)?{_RUPEE_NUM}",
    ),
    _pat("opening_balance_paise", rf"Previous\s+(?:Balance|Due)[^\d₹]*(?:₹\s*)?{_RUPEE_NUM}"),
]

_PERIOD = re.compile(
    r"(?:Statement|Billing)\s+Period[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s*[-–to]+\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
    re.I,
)


def _rupees_to_paise_safe(s: str) -> int | None:
    try:
        return parse_amount_rupees(s)
    except ValueError:
        return None


def parse_credit_card_summary(text: str) -> dict[str, Any]:
    """Best-effort summary fields from raw PDF text (paise integers)."""
    out: dict[str, Any] = {}
    for rx, key in _PATTERNS:
        m = rx.search(text)
        if not m:
            continue
        p = _rupees_to_paise_safe(m.group(1))
        if p is not None:
            out[key] = p

    pm = _PERIOD.search(text)
    if pm:
        try:
            out["period_start"] = parse_transaction_date(pm.group(1)).isoformat()
            out["period_end"] = parse_transaction_date(pm.group(2)).isoformat()
        except ValueError:
            pass

    return out


def heuristic_line_items_from_text(text: str) -> list[dict[str, Any]]:
    """Transaction-like lines using the same heuristics as bank statements."""
    rows = heuristic_rows_from_statement_text(text)
    out: list[dict[str, Any]] = []
    for r in rows[:MAX_LINE_ITEMS]:
        try:
            ap = parse_amount_rupees(r["amount"])
        except ValueError:
            continue
        desc = (r.get("merchant") or "")[:500]
        cls = _classify_cc_description(desc)
        if cls["skip"]:
            continue
        cat = cls["category"] or r.get("category") or "Other"
        out.append(
            {
                "date": r["date"],
                "amount_paise": ap,
                "description": desc,
                "category": cat,
                "payment_mode": r.get("payment_mode") or PaymentMode.OTHER_CC.value,
                "transaction_type": cls["transaction_type"],
            }
        )
    return out


def line_items_from_tabular_rows(
    raw_rows: list[dict[str, str]],
    *,
    default_payment_mode: str,
    classify: ClassifyFn | None = None,
) -> list[dict[str, Any]]:
    """Parse CSV/XLSX rows; requires date + amount; category defaults to Other."""
    out: list[dict[str, Any]] = []
    for raw in raw_rows[:MAX_LINE_ITEMS]:
        canon = canonical_row_for_import(raw)
        if "payment_mode" not in canon:
            canon["payment_mode"] = default_payment_mode
        try:
            parsed = parse_import_row(canon, classify=classify)
        except ValueError:
            continue
        desc = (parsed.merchant or "")[:500]
        cls = _classify_cc_description(desc)
        if cls["skip"]:
            continue
        cat = cls["category"] or parsed.category or "Other"
        out.append(
            {
                "date": parsed.tx_date.isoformat(),
                "amount_paise": parsed.amount_paise,
                "description": desc,
                "category": cat,
                "payment_mode": parsed.payment_mode,
                "transaction_type": cls["transaction_type"],
            }
        )
    return out


def import_rows_to_cc_line_items(
    rows: list[dict[str, str]],
    *,
    default_payment_mode: str,
    classify: ClassifyFn | None = None,
) -> list[dict[str, Any]]:
    """Map bank-statement PDF import rows (same shape as CSV) to credit-card line_items JSON."""
    out: list[dict[str, Any]] = []
    for r in rows[:MAX_LINE_ITEMS]:
        canon = {k: v for k, v in r.items() if isinstance(v, str)}
        pm = str(canon.get("payment_mode", "")).strip()
        if not pm:
            canon = {**canon, "payment_mode": default_payment_mode}
        try:
            parsed = parse_import_row(canon, classify=classify)
        except ValueError:
            continue
        desc = (parsed.merchant or "").strip()
        if parsed.notes and str(parsed.notes).strip():
            n = str(parsed.notes).strip()
            desc = f"{desc} · {n}" if desc else n
        desc = desc[:500]
        if not desc:
            desc = (parsed.merchant or "Transaction")[:500]
        cls = _classify_cc_description(desc)
        if cls["skip"]:
            continue
        cat = cls["category"] or parsed.category or "Other"
        out.append(
            {
                "date": parsed.tx_date.isoformat(),
                "amount_paise": parsed.amount_paise,
                "description": desc,
                "category": cat,
                "payment_mode": parsed.payment_mode,
                "transaction_type": cls["transaction_type"],
            }
        )
    return out


def truncate_preview(text: str) -> str:
    if len(text) <= MAX_EXTRACTION_PREVIEW:
        return text
    return text[: MAX_EXTRACTION_PREVIEW - 3] + "..."


def summary_json_dumps(summary: dict[str, Any]) -> str:
    return json.dumps(summary, ensure_ascii=False)


def line_items_json_dumps(items: list[dict[str, Any]]) -> str:
    return json.dumps(items, ensure_ascii=False)


def line_items_json_loads(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [x for x in data if isinstance(x, dict)]


def summary_json_loads(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def infer_cc_payment_mode(issuer: str | None) -> str:
    u = (issuer or "").upper()
    if "HDFC" in u:
        return PaymentMode.HDFC_CC.value
    if "SBI" in u:
        return PaymentMode.SBI_CC.value
    if "ICICI" in u:
        return PaymentMode.ICICI_CC.value
    if "AXIS" in u:
        return PaymentMode.AXIS_CC.value
    return PaymentMode.OTHER_CC.value
