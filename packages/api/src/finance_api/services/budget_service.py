"""Budget vs spend for a calendar month."""

from __future__ import annotations

import calendar
from datetime import date
from typing import Literal

import aiosqlite

from finance_api.schemas.budget import BudgetVsActualRow
from finance_common.repositories import budgets as budget_repo
from finance_common.repositories import transactions as tx_repo
from finance_common.types import Category


def _month_bounds(y: int, m: int) -> tuple[date, date]:
    last = calendar.monthrange(y, m)[1]
    return date(y, m, 1), date(y, m, last)


def _row_status(
    budget_paise: int | None, spent_paise: int
) -> tuple[float | None, Literal["none", "ok", "warn", "over", "full"]]:
    if budget_paise is None or budget_paise <= 0:
        return None, "none"
    pct = spent_paise / budget_paise
    if spent_paise > budget_paise:
        return pct, "over"
    if spent_paise == budget_paise:
        return pct, "full"
    if pct >= 0.75:
        return pct, "warn"
    return pct, "ok"


async def build_vs_actual(
    conn: aiosqlite.Connection,
    *,
    fy: str,
    year: int,
    month: int,
) -> tuple[str, list[BudgetVsActualRow]]:
    """Calendar-month spend vs effective FY budgets."""
    budget_rows = await budget_repo.effective_budgets_for_fy(conn, fy)
    budget_map: dict[str, int] = {r.category: r.monthly_amount_paise for r in budget_rows}

    start, end = _month_bounds(year, month)
    spent_map = await tx_repo.sum_by_category_month(conn, start=start, end=end)

    all_categories: set[str] = {c.value for c in Category} | set(spent_map) | set(budget_map)

    ordered: list[str] = [c.value for c in Category]
    for name in sorted(all_categories):
        if name not in ordered:
            ordered.append(name)

    label = f"{year:04d}-{month:02d}"
    rows: list[BudgetVsActualRow] = []

    for cat in ordered:
        spent = int(spent_map.get(cat, 0))
        b_raw = budget_map.get(cat)
        pct, st = _row_status(b_raw, spent)
        rows.append(
            BudgetVsActualRow(
                category=cat,
                budget_paise=b_raw,
                spent_paise=spent,
                pct_of_budget=round(pct, 4) if pct is not None else None,
                status=st,
            ),
        )

    return label, rows
