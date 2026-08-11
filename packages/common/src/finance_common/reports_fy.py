"""FY spending and summary (shared by API and Discord bot)."""

from __future__ import annotations

import aiosqlite

from finance_common.fy import fy_info, month_label
from finance_common.ledger import reports as ledger_reports
from finance_common.project_config import load_project_config
from finance_common.repositories import income_sources as income_repo
from finance_common.repositories import transactions
from finance_common.types import FYYear


async def build_fy_spending(
    conn: aiosqlite.Connection,
    fy: FYYear,
) -> tuple[str, list[dict[str, object]], int]:
    info = fy_info(fy)
    project_config = await load_project_config(conn)
    use_ledger = project_config.ledger_engine == "double_entry"
    rows: list[dict[str, object]] = []
    total = 0
    for month_num, start, end in info.months:
        if use_ledger:
            spent = await ledger_reports.budget_spend_total(conn, start=start, end=end)
        else:
            spent = await transactions.sum_between(conn, start=start, end=end)
        total += spent
        rows.append(
            {
                "fy_month": month_num,
                "label": month_label(month_num),
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "spent_paise": spent,
            },
        )
    return str(fy), rows, total


async def build_fy_summary(conn: aiosqlite.Connection, fy: FYYear) -> tuple[str, int, int, int]:
    fy_s, _, total_spent = await build_fy_spending(conn, fy)
    info = fy_info(fy)
    project_config = await load_project_config(conn)
    if project_config.ledger_engine == "double_entry":
        fy_income = await ledger_reports.income_credits_total(
            conn, start=info.start, end=info.end
        )
        # Present as annualized run-rate for the same summary shape as legacy.
        run_rate_annual = fy_income
    else:
        monthly = await income_repo.total_monthly_equivalent_paise(conn)
        run_rate_annual = monthly * 12
    implied = run_rate_annual - total_spent
    return fy_s, total_spent, run_rate_annual, implied
