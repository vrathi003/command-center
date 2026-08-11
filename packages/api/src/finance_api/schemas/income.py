"""Income stream schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class IncomeOut(BaseModel):
    id: int
    name: str
    type: str
    amount_paise: int | None
    frequency: str
    taxability: str
    is_active: bool
    default_account_id: int | None = None
    category: str | None = None
    monthly_equivalent_paise: int = Field(
        description="Amount normalized to a monthly run-rate for budgeting.",
    )


class IncomeSummaryOut(BaseModel):
    stream_count: int
    total_monthly_equivalent_paise: int


class IncomeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: str = Field(min_length=1, max_length=80)
    amount_paise: int | None = Field(default=None, ge=0)
    frequency: str = Field(description="monthly | quarterly | annual | one_time")
    taxability: str = Field(description="fully_taxable | partially_exempt | fully_exempt")
    is_active: bool = True
    default_account_id: int | None = None
    category: str | None = Field(default=None, max_length=80)


class IncomePut(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: str = Field(min_length=1, max_length=80)
    amount_paise: int | None = Field(default=None, ge=0)
    frequency: str
    taxability: str
    is_active: bool = True
    default_account_id: int | None = None
    category: str | None = Field(default=None, max_length=80)


class RecordIncomeBody(BaseModel):
    date: str
    amount_paise: int | None = Field(default=None, gt=0)
    account_id: int | None = Field(default=None, gt=0)
    category: str | None = Field(default=None, max_length=80)


class RecordIncomeOut(BaseModel):
    ledger_transaction_id: int
    income: IncomeOut
