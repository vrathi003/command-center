"""Request and response schemas for reconciliation workspaces."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class StatementCreate(BaseModel):
    account_id: int = Field(gt=0)
    period_start: date
    period_end: date
    opening_balance_paise: int
    closing_balance_paise: int
    source: str = Field(default="manual", min_length=1, max_length=100)
    filename: str | None = Field(default=None, max_length=255)


class StatementResponse(StatementCreate):
    id: int
    status: Literal["open", "reconciled"]
    created_at: str
    updated_at: str


class StatementCreated(BaseModel):
    id: int
    line_count: int


class StatementLineResponse(BaseModel):
    id: int
    statement_id: int
    tx_date: date
    amount_paise: int
    direction: Literal["in", "out"]
    payee: str | None
    narration: str | None
    external_key: str | None
    status: Literal["unmatched", "matched", "ignored"]
    ignore_reason: str | None
    created_at: str
    updated_at: str


class MatchResponse(BaseModel):
    id: int
    line_id: int
    ledger_transaction_id: int
    method: Literal["suggested", "manual"]
    confirmed_at: str


class PeriodStatusResponse(BaseModel):
    statement_id: int
    ledger_balance_paise: int
    statement_closing_balance_paise: int
    balance_difference_paise: int
    unmatched_line_count: int
    unmatched_ledger_count: int
    is_balanced: bool
    can_soft_close: bool


class StatementWorkspaceResponse(BaseModel):
    statement: StatementResponse
    lines: list[StatementLineResponse]
    matches: list[MatchResponse]
    period_status: PeriodStatusResponse


class MatchProposalResponse(BaseModel):
    line_id: int
    ledger_transaction_id: int
    score: float
    reasons: list[str]


class MatchSuggestionsResponse(BaseModel):
    proposals: list[MatchProposalResponse]


class ConfirmMatchBody(BaseModel):
    ledger_transaction_id: int = Field(gt=0)
    method: Literal["suggested", "manual"] = "manual"


class ConfirmMatchResponse(BaseModel):
    match_id: int
    line_status: Literal["matched"]


class IgnoreLineBody(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class AdjustmentBody(BaseModel):
    line_id: int = Field(gt=0)
    counterpart_account_id: int = Field(gt=0)
    category: str = Field(min_length=1, max_length=100)
    payee: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=2_000)


class AdjustmentResponse(BaseModel):
    ledger_transaction_id: int
    line_id: int
