"""Investment and fixed-income ledger account binding and opening seeds."""

from __future__ import annotations

from datetime import date

import aiosqlite

from finance_common.ledger import service as ledger_service
from finance_common.ledger.errors import LedgerError
from finance_common.ledger.models import NewPosting, PostTransactionInput
from finance_common.repositories import accounts as accounts_repo
from finance_common.repositories import fixed_income as fi_repo
from finance_common.repositories import investments as inv_repo
from finance_common.repositories.fixed_income import FixedIncomeRow
from finance_common.repositories.investments import InvestmentRow
from finance_common.types import AccountClass

_OPENING_BALANCE_EQUITY = "Opening Balance Equity"
_SEED_SOURCE = "wealth_seed"


async def _opening_balance_equity_id(conn: aiosqlite.Connection) -> int:
    account = await accounts_repo.get_account_by_name(conn, _OPENING_BALANCE_EQUITY)
    if account is None:
        raise LedgerError(f"Required system account {_OPENING_BALANCE_EQUITY!r} does not exist")
    return account.id


def investment_cost_paise(inv_row: InvestmentRow) -> int:
    if inv_row.units is not None and inv_row.avg_price_paise is not None:
        return int(round(inv_row.units * inv_row.avg_price_paise))
    return 0


async def _opening_balance_seed_plan(
    conn: aiosqlite.Connection,
    *,
    asset_account_id: int,
    amount_paise: int,
    external_key: str,
    notes: str,
    tx_date: date | None = None,
) -> PostTransactionInput:
    equity_id = await _opening_balance_equity_id(conn)
    postings = (
        NewPosting(asset_account_id, amount_paise),
        NewPosting(equity_id, -amount_paise),
    )
    return PostTransactionInput(
        tx_date=tx_date or date.today(),
        postings=postings,
        notes=notes,
        source=_SEED_SOURCE,
        external_key=external_key,
    )


async def _ensure_investment_account(conn: aiosqlite.Connection, inv_row: InvestmentRow) -> int:
    if inv_row.account_id is not None:
        return inv_row.account_id
    account_id = await accounts_repo.create_account(
        conn,
        name=inv_row.instrument.strip(),
        type="investment",
        institution=None,
        account_class=AccountClass.ASSET_INVESTMENT.value,
    )
    await inv_repo.set_investment_account_id(conn, inv_row.id, account_id)
    return account_id


async def _ensure_fixed_income_account(conn: aiosqlite.Connection, fi_row: FixedIncomeRow) -> int:
    if fi_row.account_id is not None:
        return fi_row.account_id
    account_id = await accounts_repo.create_account(
        conn,
        name=fi_row.institution.strip(),
        type="investment",
        institution=fi_row.type.strip() if fi_row.type else None,
        account_class=AccountClass.ASSET_INVESTMENT.value,
    )
    await fi_repo.set_fixed_income_account_id(conn, fi_row.id, account_id)
    return account_id


async def ensure_investment_account_and_seed(
    conn: aiosqlite.Connection, inv_row: InvestmentRow
) -> int:
    """Create asset_investment account if needed; seed cost vs Opening Balance Equity once."""
    account_id = await _ensure_investment_account(conn, inv_row)
    amount = investment_cost_paise(inv_row)
    if amount <= 0:
        return account_id
    plan = await _opening_balance_seed_plan(
        conn,
        asset_account_id=account_id,
        amount_paise=amount,
        external_key=f"inv_seed:{inv_row.id}",
        notes=f"Opening cost seed — {inv_row.instrument}",
    )
    await ledger_service.post(conn, plan)
    return account_id


async def ensure_fixed_income_account_and_seed(
    conn: aiosqlite.Connection, fi_row: FixedIncomeRow
) -> int:
    """Create asset_investment account if needed; seed principal vs Opening Balance Equity once."""
    account_id = await _ensure_fixed_income_account(conn, fi_row)
    amount = fi_row.principal_paise
    if amount <= 0:
        return account_id
    plan = await _opening_balance_seed_plan(
        conn,
        asset_account_id=account_id,
        amount_paise=amount,
        external_key=f"fi_seed:{fi_row.id}",
        notes=f"Opening principal seed — {fi_row.institution}",
    )
    await ledger_service.post(conn, plan)
    return account_id


async def ensure_all_wealth_seeds(conn: aiosqlite.Connection) -> None:
    """Bind and seed all investment and fixed-income holdings (idempotent)."""
    for inv_row in await inv_repo.list_investments(conn):
        await ensure_investment_account_and_seed(conn, inv_row)
    for fi_row in await fi_repo.list_fixed_income(conn):
        await ensure_fixed_income_account_and_seed(conn, fi_row)
