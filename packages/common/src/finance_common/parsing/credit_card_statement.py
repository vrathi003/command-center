"""Parse credit card statement text (PDF extract) and tabular exports for review/import."""

from __future__ import annotations

import json
import re
from typing import Any

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
        out.append(
            {
                "date": r["date"],
                "amount_paise": ap,
                "description": (r.get("merchant") or "")[:500],
                "category": r.get("category") or "Other",
                "payment_mode": r.get("payment_mode") or PaymentMode.OTHER_CC.value,
            }
        )
    return out


def line_items_from_tabular_rows(
    raw_rows: list[dict[str, str]],
    *,
    default_payment_mode: str,
) -> list[dict[str, Any]]:
    """Parse CSV/XLSX rows; requires date + amount; category defaults to Other."""
    out: list[dict[str, Any]] = []
    for raw in raw_rows[:MAX_LINE_ITEMS]:
        canon = canonical_row_for_import(raw)
        if "payment_mode" not in canon:
            canon["payment_mode"] = default_payment_mode
        try:
            parsed = parse_import_row(canon)
        except ValueError:
            continue
        out.append(
            {
                "date": parsed.tx_date.isoformat(),
                "amount_paise": parsed.amount_paise,
                "description": (parsed.merchant or "")[:500],
                "category": parsed.category,
                "payment_mode": parsed.payment_mode,
            }
        )
    return out


def import_rows_to_cc_line_items(
    rows: list[dict[str, str]],
    *,
    default_payment_mode: str,
) -> list[dict[str, Any]]:
    """Map bank-statement PDF import rows (same shape as CSV) to credit-card line_items JSON."""
    out: list[dict[str, Any]] = []
    for r in rows[:MAX_LINE_ITEMS]:
        canon = {k: v for k, v in r.items() if isinstance(v, str)}
        pm = str(canon.get("payment_mode", "")).strip()
        if not pm:
            canon = {**canon, "payment_mode": default_payment_mode}
        try:
            parsed = parse_import_row(canon)
        except ValueError:
            continue
        desc = (parsed.merchant or "").strip()
        if parsed.notes and str(parsed.notes).strip():
            n = str(parsed.notes).strip()
            desc = f"{desc} · {n}" if desc else n
        desc = desc[:500]
        if not desc:
            desc = (parsed.merchant or "Transaction")[:500]
        out.append(
            {
                "date": parsed.tx_date.isoformat(),
                "amount_paise": parsed.amount_paise,
                "description": desc,
                "category": parsed.category,
                "payment_mode": parsed.payment_mode,
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
