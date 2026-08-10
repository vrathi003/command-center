"""External-key generation and soft duplicate detection for intake."""

from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta

import aiosqlite

_PAYEE_PREFIX_LEN = 12
_MIN_PAYEE_PREFIX_LEN = 3


def _normalize_narration(narration: str) -> str:
    return " ".join(narration.split())


def _fingerprint(
    *, date: str, amount_paise: int, narration: str, account_id: int | None
) -> str:
    account = "" if account_id is None else str(account_id)
    return f"{date}|{amount_paise}|{_normalize_narration(narration)}|{account}"


def make_external_key(
    *,
    source: str,
    provider_id: str | None,
    date: str,
    amount_paise: int,
    narration: str,
    account_id: int | None,
) -> str:
    """Prefer provider_id; else sha256 of statement-line fingerprint."""
    if provider_id is not None:
        return f"{source}:{provider_id}"
    digest = hashlib.sha256(
        _fingerprint(
            date=date,
            amount_paise=amount_paise,
            narration=narration,
            account_id=account_id,
        ).encode()
    ).hexdigest()
    return f"{source}:{digest}"


def _normalize_payee(payee: str | None) -> str:
    if payee is None:
        return ""
    normalized = re.sub(r"\s+", " ", payee.strip().lower())
    return normalized


def _payees_match(left: str | None, right: str | None) -> bool:
    left_norm = _normalize_payee(left)
    right_norm = _normalize_payee(right)
    if not left_norm or not right_norm:
        return left_norm == right_norm
    prefix_len = min(_PAYEE_PREFIX_LEN, len(left_norm), len(right_norm))
    if prefix_len < _MIN_PAYEE_PREFIX_LEN:
        return left_norm == right_norm
    return left_norm[:prefix_len] == right_norm[:prefix_len]


def _date_bounds(tx_date: date, window_days: int) -> tuple[str, str]:
    start = tx_date - timedelta(days=window_days)
    end = tx_date + timedelta(days=window_days)
    return start.isoformat(), end.isoformat()


async def _ledger_soft_match(
    conn: aiosqlite.Connection,
    *,
    account_id: int,
    amount_paise: int,
    tx_date: date,
    payee: str | None,
    window_days: int,
) -> int | None:
    start, end = _date_bounds(tx_date, window_days)
    cursor = await conn.execute(
        """
        SELECT lt.id, lt.payee
        FROM ledger_transactions lt
        JOIN ledger_postings lp ON lp.transaction_id = lt.id
        WHERE lt.status = 'posted'
          AND lt.date BETWEEN ? AND ?
          AND lp.account_id = ?
          AND ABS(lp.amount_paise) = ?
        ORDER BY lt.id
        """,
        (start, end, account_id, amount_paise),
    )
    for row in await cursor.fetchall():
        if _payees_match(payee, None if row[1] is None else str(row[1])):
            return int(row[0])
    return None


async def _intake_soft_match(
    conn: aiosqlite.Connection,
    *,
    account_id: int,
    amount_paise: int,
    tx_date: date,
    payee: str | None,
    window_days: int,
) -> int | None:
    start, end = _date_bounds(tx_date, window_days)
    cursor = await conn.execute(
        """
        SELECT id, payee
        FROM intake_candidates
        WHERE status IN ('pending', 'posted')
          AND suggested_account_id = ?
          AND amount_paise = ?
          AND tx_date BETWEEN ? AND ?
        ORDER BY id
        """,
        (account_id, amount_paise, start, end),
    )
    for row in await cursor.fetchall():
        if _payees_match(payee, None if row[1] is None else str(row[1])):
            return int(row[0])
    return None


async def find_soft_duplicate(
    conn: aiosqlite.Connection,
    *,
    account_id: int,
    amount_paise: int,
    tx_date: date,
    payee: str | None,
    window_days: int,
) -> int | None:
    """Return intake_candidates.id or ledger tx id of soft match; None if none.

    Soft match: same account_id, amount, date±window, normalized payee prefix.
    """
    ledger_match = await _ledger_soft_match(
        conn,
        account_id=account_id,
        amount_paise=amount_paise,
        tx_date=tx_date,
        payee=payee,
        window_days=window_days,
    )
    if ledger_match is not None:
        return ledger_match
    return await _intake_soft_match(
        conn,
        account_id=account_id,
        amount_paise=amount_paise,
        tx_date=tx_date,
        payee=payee,
        window_days=window_days,
    )
