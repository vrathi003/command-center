"""Investment and fixed-income ledger account binding and opening seeds."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import aiosqlite

from finance_common.ledger import builders
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


def _weighted_avg_price_paise(
    *,
    old_units: float,
    old_avg_paise: int,
    buy_units: float,
    buy_amount_paise: int,
) -> int:
    new_units = old_units + buy_units
    if new_units <= 0:
        return int(round(buy_amount_paise / buy_units))
    total_cost = old_units * old_avg_paise + buy_amount_paise
    return int(round(total_cost / new_units))


async def record_investment_buy(
    conn: aiosqlite.Connection,
    *,
    inv_row: InvestmentRow,
    tx_date: date,
    amount_paise: int,
    units: float,
    bank_account_id: int,
    kind: str = "buy",
) -> tuple[int, InvestmentRow]:
    """Post buy/SIP through ledger; update units and weighted average cost."""
    if amount_paise <= 0:
        raise LedgerError("amount_paise must be positive")
    if units <= 0:
        raise LedgerError("units must be positive")

    bank = await accounts_repo.get_account(conn, bank_account_id)
    if bank is None:
        raise LedgerError("bank_account_id not found")

    investment_account_id = await _ensure_investment_account(conn, inv_row)
    refreshed = await inv_repo.get_investment(conn, inv_row.id)
    if refreshed is None:
        raise LedgerError("investment not found after ensure")

    old_units = refreshed.units or 0.0
    old_avg = refreshed.avg_price_paise or 0
    new_units = old_units + units
    new_avg = _weighted_avg_price_paise(
        old_units=old_units,
        old_avg_paise=old_avg,
        buy_units=units,
        buy_amount_paise=amount_paise,
    )

    label = "SIP" if kind == "sip" else "Buy"
    postings = builders.build_investment_buy(
        bank_id=bank_account_id,
        investment_account_id=investment_account_id,
        amount_paise=amount_paise,
    )
    ledger_transaction_id = await ledger_service.post(
        conn,
        PostTransactionInput(
            tx_date=tx_date,
            postings=postings,
            payee=refreshed.instrument,
            notes=f"Investment {label} — {refreshed.instrument}",
            source="investment",
            external_key=(
                f"inv_{kind}:{refreshed.id}:{tx_date.isoformat()}:{amount_paise}:{units}"
            ),
        ),
    )

    updated = replace(
        refreshed,
        units=new_units,
        avg_price_paise=new_avg,
        account_id=investment_account_id,
    )
    await inv_repo.update_investment_row(conn, updated)
    return ledger_transaction_id, updated


async def record_investment_sell(
    conn: aiosqlite.Connection,
    *,
    inv_row: InvestmentRow,
    tx_date: date,
    amount_paise: int,
    units: float,
    bank_account_id: int,
) -> tuple[int, InvestmentRow]:
    """Post sell through ledger; reduce units (avg unchanged)."""
    if amount_paise <= 0:
        raise LedgerError("amount_paise must be positive")
    if units <= 0:
        raise LedgerError("units must be positive")

    bank = await accounts_repo.get_account(conn, bank_account_id)
    if bank is None:
        raise LedgerError("bank_account_id not found")

    investment_account_id = await _ensure_investment_account(conn, inv_row)
    refreshed = await inv_repo.get_investment(conn, inv_row.id)
    if refreshed is None:
        raise LedgerError("investment not found after ensure")

    old_units = refreshed.units or 0.0
    new_units = max(0.0, old_units - units)

    postings = builders.build_investment_sell(
        bank_id=bank_account_id,
        investment_account_id=investment_account_id,
        amount_paise=amount_paise,
    )
    ledger_transaction_id = await ledger_service.post(
        conn,
        PostTransactionInput(
            tx_date=tx_date,
            postings=postings,
            payee=refreshed.instrument,
            notes=f"Investment Sell — {refreshed.instrument}",
            source="investment",
            external_key=(
                f"inv_sell:{refreshed.id}:{tx_date.isoformat()}:{amount_paise}:{units}"
            ),
        ),
    )

    updated = replace(
        refreshed,
        units=new_units,
        account_id=investment_account_id,
    )
    await inv_repo.update_investment_row(conn, updated)
    return ledger_transaction_id, updated


async def record_fixed_income_deposit(
    conn: aiosqlite.Connection,
    *,
    fi_row: FixedIncomeRow,
    tx_date: date,
    amount_paise: int,
    bank_account_id: int,
) -> tuple[int, FixedIncomeRow]:
    """Post deposit through ledger; increase principal."""
    if amount_paise <= 0:
        raise LedgerError("amount_paise must be positive")

    bank = await accounts_repo.get_account(conn, bank_account_id)
    if bank is None:
        raise LedgerError("bank_account_id not found")

    fi_account_id = await _ensure_fixed_income_account(conn, fi_row)
    refreshed = await fi_repo.get_fixed_income(conn, fi_row.id)
    if refreshed is None:
        raise LedgerError("fixed income not found after ensure")

    new_principal = refreshed.principal_paise + amount_paise

    postings = builders.build_investment_buy(
        bank_id=bank_account_id,
        investment_account_id=fi_account_id,
        amount_paise=amount_paise,
    )
    ledger_transaction_id = await ledger_service.post(
        conn,
        PostTransactionInput(
            tx_date=tx_date,
            postings=postings,
            payee=refreshed.institution,
            notes=f"Fixed income Deposit — {refreshed.institution}",
            source="fixed_income",
            external_key=(
                f"fi_deposit:{refreshed.id}:{tx_date.isoformat()}:{amount_paise}"
            ),
        ),
    )

    updated = replace(
        refreshed,
        principal_paise=new_principal,
        account_id=fi_account_id,
    )
    await fi_repo.update_fixed_income_row(conn, updated)
    return ledger_transaction_id, updated


async def record_fixed_income_maturity(
    conn: aiosqlite.Connection,
    *,
    fi_row: FixedIncomeRow,
    tx_date: date,
    amount_paise: int,
    bank_account_id: int,
) -> tuple[int, FixedIncomeRow]:
    """Post maturity/withdrawal through ledger; reduce principal (min 0)."""
    if amount_paise <= 0:
        raise LedgerError("amount_paise must be positive")

    bank = await accounts_repo.get_account(conn, bank_account_id)
    if bank is None:
        raise LedgerError("bank_account_id not found")

    fi_account_id = await _ensure_fixed_income_account(conn, fi_row)
    refreshed = await fi_repo.get_fixed_income(conn, fi_row.id)
    if refreshed is None:
        raise LedgerError("fixed income not found after ensure")

    new_principal = max(0, refreshed.principal_paise - amount_paise)

    postings = builders.build_investment_sell(
        bank_id=bank_account_id,
        investment_account_id=fi_account_id,
        amount_paise=amount_paise,
    )
    ledger_transaction_id = await ledger_service.post(
        conn,
        PostTransactionInput(
            tx_date=tx_date,
            postings=postings,
            payee=refreshed.institution,
            notes=f"Fixed income Maturity — {refreshed.institution}",
            source="fixed_income",
            external_key=(
                f"fi_maturity:{refreshed.id}:{tx_date.isoformat()}:{amount_paise}"
            ),
        ),
    )

    updated = replace(
        refreshed,
        principal_paise=new_principal,
        account_id=fi_account_id,
    )
    await fi_repo.update_fixed_income_row(conn, updated)
    return ledger_transaction_id, updated
