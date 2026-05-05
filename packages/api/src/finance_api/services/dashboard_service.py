"""Aggregate dashboard metrics from SQLite."""

from __future__ import annotations

import calendar
from datetime import date, timedelta

import aiosqlite

from finance_api.schemas.dashboard import DashboardSummary
from finance_common.repositories import income_sources as income_repo
from finance_common.repositories import settings_repo, transactions
from finance_common.types import FYYear


async def _sum_debt(conn: aiosqlite.Connection) -> int:
    cur = await conn.execute(
        """
        SELECT COALESCE(SUM(current_balance_paise), 0) FROM debts
        WHERE status = 'active'
        """,
    )
    row = await cur.fetchone()
    return int(row[0]) if row else 0


async def _latest_net_worth(conn: aiosqlite.Connection) -> int | None:
    cur = await conn.execute(
        "SELECT net_worth_paise FROM net_worth_history ORDER BY snapshot_date DESC LIMIT 1",
    )
    row = await cur.fetchone()
    return int(row[0]) if row else None


async def _portfolio_market_value(conn: aiosqlite.Connection) -> int:
    cur = await conn.execute(
        """
        SELECT COALESCE(SUM(COALESCE(units, 0) * COALESCE(current_price_paise, 0)), 0)
        FROM investments
        """,
    )
    row = await cur.fetchone()
    return int(row[0]) if row else 0


def _month_bounds(d: date) -> tuple[date, date]:
    last = calendar.monthrange(d.year, d.month)[1]
    return date(d.year, d.month, 1), date(d.year, d.month, last)


def _week_bounds(d: date) -> tuple[date, date]:
    start = d - timedelta(days=d.weekday())
    end = start + timedelta(days=6)
    return start, end


async def build_summary(
    conn: aiosqlite.Connection, *, today: date | None = None
) -> DashboardSummary:
    """Compute dashboard KPIs for the given calendar day (defaults to today)."""
    d = today or date.today()
    fy = await settings_repo.get_current_fy(conn)
    _ = FYYear(fy)  # validate shape early

    m0, m1 = _month_bounds(d)
    w0, w1 = _week_bounds(d)

    spent_today = await transactions.sum_between(conn, start=d, end=d)
    spent_week = await transactions.sum_between(conn, start=w0, end=w1)
    spent_month = await transactions.sum_between(conn, start=m0, end=m1)
    by_cat = await transactions.sum_by_category_month(conn, start=m0, end=m1)
    by_account = await transactions.sum_by_account(conn, start=m0, end=m1)

    debt = await _sum_debt(conn)
    nw = await _latest_net_worth(conn)
    port = await _portfolio_market_value(conn)
    monthly_income = await income_repo.total_monthly_equivalent_paise(conn)
    savings: float | None = None
    if monthly_income > 0:
        savings = (monthly_income - spent_month) / monthly_income

    return DashboardSummary(
        current_fy=str(fy),
        spent_today_paise=spent_today,
        spent_week_paise=spent_week,
        spent_month_paise=spent_month,
        spent_by_category_month=by_cat,
        spent_by_account_month=by_account,
        total_debt_paise=debt,
        net_worth_paise=nw,
        portfolio_value_paise=port,
        monthly_income_paise=monthly_income if monthly_income > 0 else None,
        savings_rate_month=savings,
    )
