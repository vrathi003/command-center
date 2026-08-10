"""Resolve intake candidates into balanced ledger posting plans."""

from __future__ import annotations

from datetime import date

import aiosqlite

from finance_common.intake.models import Candidate
from finance_common.ledger.builders import (
    build_bank_expense,
    build_bank_income,
    build_cc_swipe,
    build_transfer,
)
from finance_common.ledger.models import PostTransactionInput

_ASSET_CASH = "asset_cash"
_LIABILITY_CC = "liability_cc"
_UNCATEGORIZED_EXPENSE = "Uncategorized Expense"
_UNCATEGORIZED_INCOME = "Uncategorized Income"


class IntakePlanError(Exception):
    """Raised when a candidate cannot be converted into ledger postings."""


async def _account_class(conn: aiosqlite.Connection, account_id: int) -> str:
    cursor = await conn.execute(
        "SELECT account_class FROM accounts WHERE id = ?",
        (account_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        raise IntakePlanError(f"Account {account_id} does not exist")
    return str(row[0])


async def _system_account_id(conn: aiosqlite.Connection, name: str) -> int:
    cursor = await conn.execute("SELECT id FROM accounts WHERE name = ?", (name,))
    row = await cursor.fetchone()
    if row is None:
        raise IntakePlanError(f"Required system account {name!r} does not exist")
    return int(row[0])


async def _expense_account_id(conn: aiosqlite.Connection, candidate: Candidate) -> int:
    if candidate.suggested_counter_account_id is not None:
        await _account_class(conn, candidate.suggested_counter_account_id)
        return candidate.suggested_counter_account_id
    return await _system_account_id(conn, _UNCATEGORIZED_EXPENSE)


async def plan_postings(conn: aiosqlite.Connection, candidate: Candidate) -> PostTransactionInput:
    """Resolve P&L accounts and construct postings for an intake candidate."""
    if candidate.suggested_account_id is None:
        raise IntakePlanError("Candidate has no suggested account")

    account_class = await _account_class(conn, candidate.suggested_account_id)
    category = candidate.suggested_category or "Other"

    if account_class == _ASSET_CASH:
        if candidate.direction == "out":
            postings = build_bank_expense(
                bank_id=candidate.suggested_account_id,
                expense_account_id=await _expense_account_id(conn, candidate),
                amount_paise=candidate.amount_paise,
                category=category,
            )
        else:
            postings = build_bank_income(
                bank_id=candidate.suggested_account_id,
                income_account_id=await _system_account_id(conn, _UNCATEGORIZED_INCOME),
                amount_paise=candidate.amount_paise,
                category=category,
            )
    elif account_class == _LIABILITY_CC:
        if candidate.direction == "in":
            raise IntakePlanError("Credit-card payment needs a bank account")
        postings = build_cc_swipe(
            cc_id=candidate.suggested_account_id,
            expense_account_id=await _expense_account_id(conn, candidate),
            amount_paise=candidate.amount_paise,
            category=category,
        )
    else:
        raise IntakePlanError(
            f"Account {candidate.suggested_account_id} has unsupported class {account_class!r}"
        )

    return PostTransactionInput(
        tx_date=candidate.tx_date,
        postings=postings,
        payee=candidate.payee,
        notes=candidate.narration,
        source=candidate.source,
        external_key=candidate.external_key,
    )


async def plan_transfer(
    conn: aiosqlite.Connection,
    *,
    from_account_id: int,
    to_account_id: int,
    amount_paise: int,
    tx_date: date,
    source: str,
    payee: str | None = None,
    notes: str | None = None,
    external_key: str | None = None,
) -> PostTransactionInput:
    """Build a transfer plan after validating both explicitly supplied accounts."""
    await _account_class(conn, from_account_id)
    await _account_class(conn, to_account_id)
    return PostTransactionInput(
        tx_date=tx_date,
        postings=build_transfer(
            from_account_id=from_account_id,
            to_account_id=to_account_id,
            amount_paise=amount_paise,
        ),
        payee=payee,
        notes=notes,
        source=source,
        external_key=external_key,
    )
