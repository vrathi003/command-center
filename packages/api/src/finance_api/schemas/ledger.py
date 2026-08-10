"""Request and response schemas for immutable ledger entries."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

LedgerPattern = Literal[
    "bank_expense",
    "bank_income",
    "transfer",
    "cc_swipe",
    "cc_bill_pay",
    "investment_buy",
    "custom",
]


class LedgerPostingCreate(BaseModel):
    account_id: int = Field(gt=0)
    amount_paise: int
    category: str | None = Field(default=None, max_length=100)


class LedgerTransactionCreate(BaseModel):
    date: date
    pattern: LedgerPattern
    amount_paise: int | None = None
    bank_account_id: int | None = Field(default=None, gt=0)
    expense_account_id: int | None = Field(default=None, gt=0)
    income_account_id: int | None = Field(default=None, gt=0)
    from_account_id: int | None = Field(default=None, gt=0)
    to_account_id: int | None = Field(default=None, gt=0)
    cc_account_id: int | None = Field(default=None, gt=0)
    investment_account_id: int | None = Field(default=None, gt=0)
    category: str | None = Field(default=None, max_length=100)
    postings: list[LedgerPostingCreate] | None = None
    payee: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=2_000)
    tags: str | None = Field(default=None, max_length=500)
    source: str = Field(default="manual", min_length=1, max_length=100)
    external_key: str | None = Field(default=None, max_length=255)


class LedgerPostingResponse(BaseModel):
    id: int
    account_id: int
    amount_paise: int
    category: str | None


class LedgerTransactionResponse(BaseModel):
    id: int
    date: date
    payee: str | None
    notes: str | None
    tags: str | None
    source: str
    status: str
    external_key: str | None
    postings: list[LedgerPostingResponse]


class LedgerTransactionCreated(BaseModel):
    id: int


class LedgerPostingListItem(BaseModel):
    account_id: int
    amount_paise: int
    category: str | None


class LedgerTransactionListItem(BaseModel):
    id: int
    date: date
    payee: str | None
    notes: str | None
    source: str
    external_key: str | None
    status: str
    amount_paise: int
    postings: list[LedgerPostingListItem]


class LedgerAccountBalanceResponse(BaseModel):
    account_id: int
    balance_paise: int


class LedgerMonthSummaryResponse(BaseModel):
    budget_spend_month_paise: int
    cash_out_month_paise: int
    cash_in_month_paise: int
    net_worth_paise: int
    budget_spend_by_category: dict[str, int]
