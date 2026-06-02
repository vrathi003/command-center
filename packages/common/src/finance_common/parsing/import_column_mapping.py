"""Bank / export CSV column header → canonical import field mapping.

Add new banks by extending alias sets or substring rules below — no changes needed in
``transaction_import.py`` for most new statement layouts.
"""

from __future__ import annotations

import re
from typing import Literal

# Roles used while resolving headers. "meta" columns help detect header rows only.
ColumnRole = Literal[
    "date",
    "amount",
    "category",
    "merchant",
    "payment_mode",
    "notes",
    "account",
    "debit",
    "credit",
    "meta",
]

CANONICAL_FIELDS: frozenset[str] = frozenset(
    {"date", "amount", "category", "merchant", "payment_mode", "notes", "account"},
)

# When several date columns exist (e.g. Value Date + Transaction Date), pick in this order.
DATE_HEADER_PRIORITY: tuple[str, ...] = (
    "value_date",
    "booking_date",
    "book_date",
    "posted_date",
    "posting_date",
    "transaction_date",
    "txn_date",
    "tran_date",
    "date",
)

# --- Exact normalized header → role (built from alias lists) ---

_DATE_ALIASES: frozenset[str] = frozenset(
    {
        "date",
        "txn_date",
        "transaction_date",
        "posted_date",
        "value_date",
        "booking_date",
        "book_date",
        "tran_date",
        "posting_date",
    },
)

_AMOUNT_ALIASES: frozenset[str] = frozenset(
    {
        "amount",
        "rupees",
        "inr",
        "amt",
        "value",
        "txn_amount",
        "net_amount",
        "transaction_amount",
        "amount_inr",
    },
)

_DEBIT_ALIASES: frozenset[str] = frozenset(
    {
        "debit",
        "debit_amount",
        "withdrawal",
        "withdrawals",
        "withdrawal_amt",
        "withdrawal_amount",
        "dr",
        "dr_amount",
        "money_out",
        "paid_out",
    },
)

_CREDIT_ALIASES: frozenset[str] = frozenset(
    {
        "credit",
        "credit_amount",
        "deposit",
        "deposits",
        "deposit_amt",
        "deposit_amount",
        "cr",
        "cr_amount",
        "money_in",
        "received",
    },
)

_MERCHANT_ALIASES: frozenset[str] = frozenset(
    {
        "merchant",
        "payee",
        "description",
        "narration",
        "particulars",
        "particular",
        "counterparty",
        "payee_name",
        "details",
        "transaction_details",
        "transaction_remarks",
        "txn_details",
        "remarks",
        "beneficiary",
        "beneficiary_name",
    },
)

_CATEGORY_ALIASES: frozenset[str] = frozenset(
    {
        "category",
        "cat",
        "type",
        "category_name",
    },
)

_PAYMENT_MODE_ALIASES: frozenset[str] = frozenset(
    {
        "payment_mode",
        "payment",
        "mode",
        "instrument",
    },
)

_NOTES_ALIASES: frozenset[str] = frozenset(
    {
        "notes",
        "note",
        "memo",
    },
)

_ACCOUNT_ALIASES: frozenset[str] = frozenset(
    {
        "account",
        "bank_account",
    },
)

_META_ALIASES: frozenset[str] = frozenset(
    {
        "balance",
        "closing_balance",
        "running_balance",
        "available_balance",
        "chq_no",
        "cheque_no",
        "cheque_number",
        "ref_no",
        "reference_no",
        "reference_number",
        "sr_no",
        "sl_no",
        "s_no",
        "serial_no",
        "transaction_id",
        "txn_id",
        "utr_no",
        "utr",
    },
)

# (substring in normalized header, role) — longest patterns first at runtime.
_SUBSTRING_ROLE_RULES: tuple[tuple[str, ColumnRole], ...] = (
    ("withdrawal_amount", "debit"),
    ("withdrawal_amt", "debit"),
    ("deposit_amount", "credit"),
    ("deposit_amt", "credit"),
    ("debit_amount", "debit"),
    ("credit_amount", "credit"),
    ("transaction_remark", "merchant"),
    ("transaction_detail", "merchant"),
    ("value_date", "date"),
    ("booking_date", "date"),
    ("transaction_date", "date"),
    ("posting_date", "date"),
    ("withdrawal", "debit"),
    ("deposit", "credit"),
    ("particular", "merchant"),
    ("narration", "merchant"),
    ("description", "merchant"),
    ("beneficiary", "merchant"),
    ("remark", "merchant"),
    ("payee", "merchant"),
    ("debit", "debit"),
    ("credit", "credit"),
    ("balance", "meta"),
    ("cheque", "meta"),
    ("reference", "meta"),
    ("tran_date", "date"),
    ("txn_date", "date"),
)

_SUBSTRING_RULES_SORTED: tuple[tuple[str, ColumnRole], ...] = tuple(
    sorted(_SUBSTRING_ROLE_RULES, key=lambda x: len(x[0]), reverse=True),
)


def _build_exact_role_map() -> dict[str, ColumnRole]:
    mapping: dict[str, ColumnRole] = {}
    for alias in _DATE_ALIASES:
        mapping[alias] = "date"
    for alias in _AMOUNT_ALIASES:
        mapping[alias] = "amount"
    for alias in _DEBIT_ALIASES:
        mapping[alias] = "debit"
    for alias in _CREDIT_ALIASES:
        mapping[alias] = "credit"
    for alias in _MERCHANT_ALIASES:
        mapping[alias] = "merchant"
    for alias in _CATEGORY_ALIASES:
        mapping[alias] = "category"
    for alias in _PAYMENT_MODE_ALIASES:
        mapping[alias] = "payment_mode"
    for alias in _NOTES_ALIASES:
        mapping[alias] = "notes"
    for alias in _ACCOUNT_ALIASES:
        mapping[alias] = "account"
    for alias in _META_ALIASES:
        mapping[alias] = "meta"
    return mapping


_EXACT_ROLE: dict[str, ColumnRole] = _build_exact_role_map()

_ALL_KNOWN_HEADER_KEYS: frozenset[str] = frozenset(_EXACT_ROLE.keys())

_DATE_HEADER_KEYS: frozenset[str] = frozenset(k for k, v in _EXACT_ROLE.items() if v == "date")


def normalize_header_key(key: str) -> str:
    """Normalize a spreadsheet column title for lookup (lowercase, no currency suffix)."""
    s = key.strip()
    if s.startswith("\ufeff"):
        s = s[1:]
    s = s.lower().replace(" ", "_").replace("-", "_")
    s = re.sub(r"[\(\)]", "", s)
    s = re.sub(r"\.+$", "", s)
    s = re.sub(r"_(inr|usd|eur|gbp)$", "", s, flags=re.IGNORECASE)
    if s.endswith("inr") and len(s) > 3:
        s = s[:-3].rstrip("_")
    return s


def resolve_column_role(normalized_key: str) -> ColumnRole | None:
    """Map a normalized header to its import role (exact alias, then substring rules)."""
    if not normalized_key:
        return None
    exact = _EXACT_ROLE.get(normalized_key)
    if exact is not None:
        return exact
    for pattern, role in _SUBSTRING_RULES_SORTED:
        if pattern in normalized_key:
            return role
    return None


def is_recognized_header_key(normalized_key: str) -> bool:
    """True if this column is known (exact or substring rule)."""
    return resolve_column_role(normalized_key) is not None


def is_date_header_key(normalized_key: str) -> bool:
    return resolve_column_role(normalized_key) == "date"


def _pick_date_value(date_columns: list[tuple[str, str]]) -> str | None:
    if not date_columns:
        return None
    by_key = {nk: val for nk, val in date_columns}
    for preferred in DATE_HEADER_PRIORITY:
        if preferred in by_key:
            return by_key[preferred]
    return date_columns[0][1]


def _coalesce_amount_from_debit_credit(raw: dict[str, str]) -> tuple[str, str] | None:
    debit_s = ""
    credit_s = ""
    for k, v in raw.items():
        nk = normalize_header_key(k)
        role = resolve_column_role(nk)
        val = (v or "").strip()
        if not val:
            continue
        if role == "debit":
            debit_s = val
        elif role == "credit":
            credit_s = val
    if debit_s:
        return debit_s, "debit"
    if credit_s:
        return credit_s, "credit"
    return None


def _detect_transaction_type(raw: dict[str, str]) -> str:
    for k, v in raw.items():
        nk = normalize_header_key(k)
        val = (v or "").strip()
        if not val:
            continue
        role = resolve_column_role(nk)
        if role == "debit":
            return "debit"
        if role == "credit":
            return "credit"
    return "debit"


def build_canonical_import_row(raw: dict[str, str]) -> dict[str, str]:
    """Map one CSV/Excel row (original headers) to canonical import keys."""
    out: dict[str, str] = {}
    date_columns: list[tuple[str, str]] = []

    for k, v in raw.items():
        nk = normalize_header_key(k)
        role = resolve_column_role(nk)
        val = (v or "").strip()
        if not val or role is None or role == "meta":
            continue
        if role == "date":
            date_columns.append((nk, val))
            continue
        if role in ("debit", "credit"):
            continue
        if role in CANONICAL_FIELDS and role not in out:
            out[role] = val

    picked_date = _pick_date_value(date_columns)
    if picked_date:
        out["date"] = picked_date

    if "amount" not in out:
        result = _coalesce_amount_from_debit_credit(raw)
        if result:
            amt, tx_type = result
            out = {**out, "amount": amt, "transaction_type": tx_type}
    else:
        out = {**out, "transaction_type": _detect_transaction_type(raw)}

    if "date" in out and "amount" in out and "category" not in out:
        out["category"] = "Other"
    return out


def score_header_row(cells: list[str]) -> tuple[int, bool]:
    """Return (count_of_known_headers, has_date_header)."""
    count = 0
    has_date = False
    for cell in cells:
        nk = normalize_header_key(cell)
        if not nk:
            continue
        if is_recognized_header_key(nk):
            count += 1
        if is_date_header_key(nk):
            has_date = True
    return count, has_date
