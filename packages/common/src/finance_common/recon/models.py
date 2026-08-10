"""Value objects for reconciliation statements, lines, and matches."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

StatementStatus = Literal["open", "reconciled"]
LineDirection = Literal["in", "out"]
LineStatus = Literal["unmatched", "matched", "ignored"]
MatchMethod = Literal["suggested", "manual"]


@dataclass(frozen=True, slots=True)
class NewStatement:
    """Statement metadata used to create a reconciliation workspace."""

    account_id: int
    period_start: date
    period_end: date
    opening_balance_paise: int
    closing_balance_paise: int
    source: str
    filename: str | None = None


@dataclass(frozen=True, slots=True)
class NewStatementLine:
    """A normalized statement line with a positive amount and direction."""

    tx_date: date
    amount_paise: int
    direction: LineDirection
    payee: str | None = None
    narration: str | None = None
    external_key: str | None = None


@dataclass(frozen=True, slots=True)
class ReconStatement:
    """Persisted reconciliation statement metadata."""

    id: int
    account_id: int
    period_start: date
    period_end: date
    opening_balance_paise: int
    closing_balance_paise: int
    status: StatementStatus
    source: str
    filename: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class ReconStatementLine:
    """Persisted statement line."""

    id: int
    statement_id: int
    tx_date: date
    amount_paise: int
    direction: LineDirection
    payee: str | None
    narration: str | None
    external_key: str | None
    status: LineStatus
    ignore_reason: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class ReconMatch:
    """Confirmed mapping from a statement line to a ledger transaction."""

    id: int
    line_id: int
    ledger_transaction_id: int
    method: MatchMethod
    confirmed_at: str


@dataclass(frozen=True, slots=True)
class StatementWorkspace:
    """A statement and all persisted line and match rows for its workspace."""

    statement: ReconStatement
    lines: tuple[ReconStatementLine, ...]
    matches: tuple[ReconMatch, ...]
