"""Derive net worth snapshot totals from current holdings."""

from __future__ import annotations

import aiosqlite

from finance_common.repositories import assets as asset_repo
from finance_common.repositories import credit_cards as cc_repo
from finance_common.repositories import debts as debt_repo
from finance_common.repositories import fixed_income as fi_repo
from finance_common.repositories import investments as inv_repo


async def compute_totals_from_holdings(
    conn: aiosqlite.Connection,
) -> tuple[int, int, int]:
    """Assets (portfolio MV + fixed income + real assets), liabilities (active debt + CC), net."""
    _, mkt, _, _ = await inv_repo.portfolio_totals(conn)
    fi_total, _ = await fi_repo.total_principal(conn)
    debt_total, _, _ = await debt_repo.aggregate_active(conn)
    real_assets_total = await asset_repo.total_active_value(conn)
    cc_total = await cc_repo.total_outstanding_balance(conn)
    assets = mkt + fi_total + real_assets_total
    liabilities = debt_total + cc_total
    return assets, liabilities, assets - liabilities
