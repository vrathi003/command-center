"""Reducing-balance amortization — simple and phased (home loan) modes."""

from __future__ import annotations

import calendar
from datetime import date
from typing import TYPE_CHECKING

from finance_api.schemas.debt import AmortizationRow

if TYPE_CHECKING:
    from finance_common.repositories.debts import DebtRow


def build_schedule(
    balance_paise: int,
    annual_rate_percent: float | None,
    emi_paise: int | None,
    *,
    tenure_months: int | None = None,
    max_months: int = 600,
) -> tuple[list[AmortizationRow], int | None]:
    """
    Simple reducing-balance schedule.

    When tenure_months is provided the schedule is capped at that length —
    this is the authoritative duration (car loan, personal loan, CC EMI, etc.).
    When omitted the schedule runs until the balance hits zero (legacy fallback).
    """
    cap = tenure_months if tenure_months and tenure_months > 0 else max_months

    if emi_paise is None or emi_paise <= 0 or balance_paise <= 0:
        return [], None

    if annual_rate_percent is None or annual_rate_percent <= 0:
        # Zero-interest loan
        rows: list[AmortizationRow] = []
        bal = float(balance_paise)
        m = 0
        while bal > 0 and m < cap:
            m += 1
            pay = min(float(emi_paise), bal)
            rows.append(
                AmortizationRow(
                    month_index=m,
                    payment_paise=int(round(pay)),
                    interest_paise=0,
                    principal_paise=int(round(pay)),
                    balance_after_paise=max(0, int(round(bal - pay))),
                    phase="full_emi",
                ),
            )
            bal -= pay
        return rows, len(rows) if rows else None

    monthly_rate = (annual_rate_percent / 100) / 12
    balance = float(balance_paise)
    emi = float(emi_paise)
    rows = []
    m = 0
    while balance > 0.5 and m < cap:
        m += 1
        interest = balance * monthly_rate
        principal = emi - interest
        if principal <= 0:
            # EMI too small to cover interest — stop
            break
        balance -= principal
        rows.append(
            AmortizationRow(
                month_index=m,
                payment_paise=int(round(emi)),
                interest_paise=int(round(interest)),
                principal_paise=int(round(principal)),
                balance_after_paise=max(0, int(round(balance))),
                phase="full_emi",
            ),
        )
    return rows, len(rows) if rows else None


def build_phased_schedule(
    disbursals: list[tuple[str, int]],  # [(date_str, incremental_amount_paise), ...]
    annual_rate_percent: float,
    emi_paise: int,
    full_emi_start_date: str,
    tenure_months: int,
    loan_start_date: str,
) -> tuple[list[AmortizationRow], int | None]:
    """
    Phased schedule for home loans with construction-linked disbursals.

    Phase 1 — Pre-EMI (interest-only):
        Each month from loan_start_date to full_emi_start_date, the monthly
        payment = cumulative_disbursed * rate/12.  Principal stays unchanged.

    Phase 2 — Full EMI (reducing balance):
        Standard reducing-balance on total_disbursed for remaining tenure.
    """
    if not disbursals:
        return [], None

    # Sort disbursals chronologically
    sorted_d = sorted(disbursals, key=lambda x: x[0])

    start = _parse_ym(loan_start_date)
    full_emi_start = _parse_ym(full_emi_start_date)

    rows: list[AmortizationRow] = []
    month_idx = 0

    # ── Phase 1: pre-EMI ────────────────────────────────────────────────────
    current = start
    pre_emi_months = 0

    while current < full_emi_start:
        month_idx += 1
        pre_emi_months += 1

        # Cumulative disbursed up to and including this month
        cum = sum(
            amt for d_str, amt in sorted_d
            if _parse_ym(d_str) <= current
        )

        if cum <= 0:
            rows.append(AmortizationRow(
                month_index=month_idx,
                payment_paise=0,
                interest_paise=0,
                principal_paise=0,
                balance_after_paise=0,
                phase="pre_emi",
            ))
        else:
            monthly_rate = annual_rate_percent / 100 / 12
            interest = int(round(cum * monthly_rate))
            rows.append(AmortizationRow(
                month_index=month_idx,
                payment_paise=interest,
                interest_paise=interest,
                principal_paise=0,
                balance_after_paise=cum,  # balance unchanged in pre-EMI
                phase="pre_emi",
            ))

        current = _add_month(current)

    # ── Phase 2: full EMI ────────────────────────────────────────────────────
    total_disbursed = sum(amt for _, amt in sorted_d)
    remaining_tenure = max(0, tenure_months - pre_emi_months)

    if remaining_tenure <= 0 or total_disbursed <= 0:
        return rows, len(rows) if rows else None

    phase2, _ = build_schedule(
        total_disbursed,
        annual_rate_percent,
        emi_paise,
        tenure_months=remaining_tenure,
    )

    for r in phase2:
        month_idx += 1
        rows.append(AmortizationRow(
            month_index=month_idx,
            payment_paise=r.payment_paise,
            interest_paise=r.interest_paise,
            principal_paise=r.principal_paise,
            balance_after_paise=r.balance_after_paise,
            phase="full_emi",
        ))

    return rows, len(rows) if rows else None


# ── helpers ──────────────────────────────────────────────────────────────────

def _parse_ym(date_str: str) -> date:
    """Parse ISO date string and normalise to first-of-month."""
    d = date.fromisoformat(date_str[:10])
    return date(d.year, d.month, 1)


def _add_month(d: date) -> date:
    """Advance by exactly one calendar month."""
    year, month = d.year, d.month
    month += 1
    if month > 12:
        month = 1
        year += 1
    return date(year, month, 1)


def advance_months(d: date, n: int) -> date:
    """Add n months to d, clamping day to end-of-month if needed."""
    total_months = d.month - 1 + n
    year = d.year + total_months // 12
    month = total_months % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def emis_due_count(first_emi: date, as_of: date) -> int:
    """Number of EMI due dates on or before ``as_of`` (due day counts as due)."""
    if as_of < first_emi:
        return 0
    months = (as_of.year - first_emi.year) * 12 + (as_of.month - first_emi.month)
    if as_of.day >= first_emi.day:
        months += 1
    return months


def _overdue_emi_count(next_emi: date, as_of: date) -> int:
    """How many EMI due dates from ``next_emi`` through ``as_of`` (inclusive)."""
    if next_emi > as_of:
        return 0
    count = 0
    while advance_months(next_emi, count) <= as_of:
        count += 1
    return count


def compute_emi_advance(row: "DebtRow") -> tuple[int, str, str] | None:
    """
    Compute the correct EMI state for a debt based on elapsed time.

    Returns (new_balance_paise, new_next_emi_date_iso, new_status) or None
    when no update is needed (EMI not yet due, or required fields missing).

    Uses original_amount_paise (falling back to current_balance_paise) as the
    starting principal so the schedule is always computed from inception.
    Skips phased home loans (those with disbursals are handled separately).
    """
    if row.status != "active":
        return None
    if not row.emi_paise or row.emi_paise <= 0:
        return None

    today = date.today()
    schedule_ref = row.first_emi_date or row.start_date

    # Overdue when next_emi_date is on or before today.
    if row.next_emi_date:
        stored_next = date.fromisoformat(row.next_emi_date[:10])
        if stored_next > today:
            return None
    elif schedule_ref:
        ref = date.fromisoformat(schedule_ref[:10])
        if emis_due_count(ref, today) == 0:
            return None
    else:
        return None

    # Schedule-based path when we know the first payment date.
    if schedule_ref:
        ref_date = date.fromisoformat(schedule_ref[:10])
        payments_due = emis_due_count(ref_date, today)
        if payments_due == 0:
            return None

        start_paise = row.original_amount_paise or row.current_balance_paise
        sched, _ = build_schedule(
            start_paise,
            row.rate_percent,
            row.emi_paise,
            tenure_months=row.tenure_months,
        )

        if not sched:
            return None

        payments_made = min(payments_due, len(sched))

        if payments_made >= len(sched):
            return 0, advance_months(ref_date, len(sched)).isoformat(), "closed"

        new_balance = sched[payments_made - 1].balance_after_paise
        new_next_emi_date = advance_months(ref_date, payments_made)
        new_status = "active"

        if (
            row.current_balance_paise == new_balance
            and row.next_emi_date == new_next_emi_date.isoformat()
        ):
            return None
        return new_balance, new_next_emi_date.isoformat(), new_status

    # Fallback: only next_emi_date set — reduce balance by EMI × overdue months.
    assert row.next_emi_date is not None
    due = date.fromisoformat(row.next_emi_date[:10])
    overdue = _overdue_emi_count(due, today)
    if overdue == 0:
        return None

    new_next = advance_months(due, overdue)
    new_balance = max(0, row.current_balance_paise - overdue * row.emi_paise)
    new_status = "closed" if new_balance == 0 else "active"

    if row.current_balance_paise == new_balance and row.next_emi_date == new_next.isoformat():
        return None
    return new_balance, new_next.isoformat(), new_status
