"""Debt API schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DebtOut(BaseModel):
    id: int
    name: str
    lender: str | None
    type: str
    original_amount_paise: int | None
    current_balance_paise: int
    emi_paise: int | None
    rate_percent: float | None
    start_date: str | None
    next_emi_date: str | None
    status: str
    tenure_months: int | None = None
    first_emi_date: str | None = None
    full_emi_start_date: str | None = None


class DebtSummaryOut(BaseModel):
    total_outstanding_paise: int
    total_emi_monthly_paise: int
    active_count: int
    next_emi_date: str | None = None
    next_emi_debt_name: str | None = None


class DebtCreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    lender: str | None = None
    type: str = Field(min_length=1, max_length=80)
    original_amount_paise: int | None = Field(default=None, ge=0)
    current_balance_paise: int = Field(ge=0)
    emi_paise: int | None = Field(default=None, ge=0)
    rate_percent: float | None = None
    start_date: str | None = None
    next_emi_date: str | None = None
    status: str = "active"
    tenure_months: int | None = Field(default=None, ge=1, le=360)
    first_emi_date: str | None = None
    full_emi_start_date: str | None = None


class DebtPutBody(BaseModel):
    name: str | None = None
    lender: str | None = None
    type: str | None = None
    original_amount_paise: int | None = None
    current_balance_paise: int | None = None
    emi_paise: int | None = None
    rate_percent: float | None = None
    start_date: str | None = None
    next_emi_date: str | None = None
    status: str | None = None
    tenure_months: int | None = Field(default=None, ge=1, le=360)
    first_emi_date: str | None = None
    full_emi_start_date: str | None = None


class AmortizationRow(BaseModel):
    month_index: int
    payment_paise: int
    interest_paise: int
    principal_paise: int
    balance_after_paise: int
    phase: str = "full_emi"  # "pre_emi" | "full_emi"


class AmortizationResponse(BaseModel):
    debt_id: int
    rows: list[AmortizationRow]
    payoff_months: int | None = Field(
        default=None,
        description="Total months in schedule.",
    )
    is_phased: bool = False
    total_pre_emi_months: int = 0
    total_disbursed_paise: int | None = None


class LoanDisbursalOut(BaseModel):
    id: int
    debt_id: int
    disbursal_date: str
    amount_paise: int
    cumulative_paise: int
    notes: str | None
    created_at: str


class LoanDisbursalBody(BaseModel):
    disbursal_date: str
    amount_paise: int = Field(ge=1)
    notes: str | None = None
