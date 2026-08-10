"""Request and response schemas for intake quarantine review."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

CandidateStatus = Literal["pending", "posted", "rejected"]
CandidateDirection = Literal["out", "in"]


class ApproveBody(BaseModel):
    account_id: int | None = Field(default=None, gt=0)
    category: str | None = Field(default=None, max_length=100)
    counter_account_id: int | None = Field(default=None, gt=0)
    as_transfer: bool = False
    to_account_id: int | None = Field(default=None, gt=0)


class IntakeCandidateResponse(BaseModel):
    id: int
    status: CandidateStatus
    source: str
    tx_date: date
    amount_paise: int
    direction: CandidateDirection
    payee: str | None
    narration: str | None
    suggested_account_id: int | None
    suggested_counter_account_id: int | None
    suggested_category: str | None
    confidence: float
    quarantine_reason: str | None
    ledger_transaction_id: int | None
    external_key: str | None


class CandidateApprovedResponse(BaseModel):
    candidate_id: int
    ledger_transaction_id: int
    status: Literal["posted"]


class CandidateRejectedResponse(BaseModel):
    candidate_id: int
    status: Literal["rejected"]
