"""EMI auto-advance — balance + next due date when an EMI date has passed."""

from __future__ import annotations

from dataclasses import replace

import aiosqlite

from finance_api.services.amortization import compute_emi_advance
from finance_common.repositories import debts as debt_repo
from finance_common.repositories.debts import DebtRow


async def auto_advance_active_debts(conn: aiosqlite.Connection) -> int:
    """Persist balance + next_emi_date for overdue active debts. Returns count updated."""
    debts = await debt_repo.list_debts(conn, status="active")
    updated = 0
    for debt in debts:
        if await auto_advance_debt(conn, debt) is not None:
            updated += 1
    return updated


async def auto_advance_debt(conn: aiosqlite.Connection, debt: DebtRow) -> DebtRow | None:
    """Advance a single debt if its EMI is overdue. Returns updated row or None if unchanged."""
    result = compute_emi_advance(debt)
    if not result:
        return None
    new_bal, new_next_date, new_status = result
    updated = replace(
        debt,
        current_balance_paise=new_bal,
        next_emi_date=new_next_date,
        status=new_status,
    )
    await debt_repo.update_debt_row(conn, updated)
    return updated
