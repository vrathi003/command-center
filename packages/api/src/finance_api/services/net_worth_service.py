"""Derive net worth snapshot totals from current holdings."""

from __future__ import annotations

import aiosqlite

from finance_common.ledger.balances import balances_for_accounts, net_worth_totals
from finance_common.project_config import load_project_config
from finance_common.repositories import assets as asset_repo
from finance_common.repositories import credit_cards as cc_repo
from finance_common.repositories import debts as debt_repo
from finance_common.repositories import fixed_income as fi_repo
from finance_common.repositories import investments as inv_repo


async def _linked_investment_cost(conn: aiosqlite.Connection) -> int:
    rows = await inv_repo.list_investments(conn)
    account_ids = [row.account_id for row in rows if row.account_id is not None]
    if not account_ids:
        return 0
    balances = await balances_for_accounts(conn, account_ids)
    return sum(balances.values())


async def _linked_fixed_income_cost(conn: aiosqlite.Connection) -> int:
    rows = await fi_repo.list_fixed_income(conn)
    account_ids = [row.account_id for row in rows if row.account_id is not None]
    if not account_ids:
        return 0
    balances = await balances_for_accounts(conn, account_ids)
    return sum(balances.values())


async def _unbound_debt_total(conn: aiosqlite.Connection) -> int:
    cur = await conn.execute(
        """
        SELECT COALESCE(SUM(current_balance_paise), 0)
        FROM debts
        WHERE status = 'active' AND account_id IS NULL
        """,
    )
    row = await cur.fetchone()
    return int(row[0]) if row else 0


async def _unbound_cc_total(conn: aiosqlite.Connection) -> int:
    cur = await conn.execute(
        """
        SELECT COALESCE(SUM(current_balance_paise), 0)
        FROM credit_cards
        WHERE is_active = 1
          AND current_balance_paise > 0
          AND account_id IS NULL
        """,
    )
    row = await cur.fetchone()
    return int(row[0]) if row else 0


async def compute_net_worth_composed(conn: aiosqlite.Connection) -> tuple[int, int, int]:
    """Assets, liabilities, net using ledger balance sheet + MV/principal overlay."""
    base_assets, base_liabilities, _ = await net_worth_totals(conn)
    inv_cost = await _linked_investment_cost(conn)
    fi_cost = await _linked_fixed_income_cost(conn)
    _, inv_mv, _, _ = await inv_repo.portfolio_totals(conn)
    fi_principal, _ = await fi_repo.total_principal(conn)
    other_assets = await asset_repo.total_active_value(conn)
    unbound_debt = await _unbound_debt_total(conn)
    unbound_cc = await _unbound_cc_total(conn)

    assets = base_assets - inv_cost - fi_cost + inv_mv + fi_principal + other_assets
    liabilities = base_liabilities + unbound_debt + unbound_cc
    return assets, liabilities, assets - liabilities


async def _compute_totals_holdings_only(conn: aiosqlite.Connection) -> tuple[int, int, int]:
    """Assets (portfolio MV + fixed income + real assets), liabilities (active debt + CC), net."""
    _, mkt, _, _ = await inv_repo.portfolio_totals(conn)
    fi_total, _ = await fi_repo.total_principal(conn)
    debt_total, _, _ = await debt_repo.aggregate_active(conn)
    real_assets_total = await asset_repo.total_active_value(conn)
    cc_total = await cc_repo.total_outstanding_balance(conn)
    assets = mkt + fi_total + real_assets_total
    liabilities = debt_total + cc_total
    return assets, liabilities, assets - liabilities


async def compute_totals_from_holdings(
    conn: aiosqlite.Connection,
) -> tuple[int, int, int]:
    """Dispatch to composed ledger lens or legacy holdings-only compute."""
    project_config = await load_project_config(conn)
    if project_config.ledger_engine == "double_entry":
        return await compute_net_worth_composed(conn)
    return await _compute_totals_holdings_only(conn)
