"""Credit card API schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CreditCardOut(BaseModel):
    id: int
    name: str
    issuer: str | None
    last_four: str | None
    credit_limit_paise: int
    current_balance_paise: int | None
    notes: str | None
    is_active: bool
    utilization_pct: float | None = None
    emi_limit_blocked_paise: int = 0
    emi_monthly_due_paise: int = 0
    emi_active_plan_count: int = 0
    total_limit_used_paise: int = 0


class CreditCardCreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    issuer: str | None = Field(default=None, max_length=120)
    last_four: str | None = Field(default=None, max_length=4)
    credit_limit_paise: int = Field(ge=0)
    current_balance_paise: int | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=2000)
    is_active: bool = True


class CreditCardPutBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    issuer: str | None = Field(default=None, max_length=120)
    last_four: str | None = Field(default=None, max_length=4)
    credit_limit_paise: int | None = Field(default=None, ge=0)
    current_balance_paise: int | None = None
    notes: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None


class CreditCardStatementOut(BaseModel):
    id: int
    credit_card_id: int
    filename: str
    period_start: str | None
    period_end: str | None
    extraction_preview: str | None
    summary: dict[str, Any]
    line_items: list[dict[str, Any]]
    status: str
    created_at: str | None = None


class CreditCardStatementApplyResponse(BaseModel):
    imported_count: int
    updated_balance_paise: int | None = None


class CreditCardEmiOut(BaseModel):
    id: int
    credit_card_id: int
    description: str
    limit_blocked_paise: int
    emi_amount_paise: int
    tenure_months: int
    installments_paid: int
    is_active: bool
    notes: str | None
    loan_type: str | None = None
    creation_date: str | None = None
    finish_date: str | None = None
    principal_paise: int | None = None
    outstanding_instalment_paise: int | None = None
    installments_remaining: int
    pending_installments: int
    principal_basis_paise: int
    total_repayment_schedule_paise: int
    total_interest_estimated_paise: int
    interest_over_principal_pct: float | None = None
    amount_paid_to_date_paise: int
    interest_paid_estimated_paise: int
    interest_remaining_estimated_paise: int


class CreditCardEmiCreateBody(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    limit_blocked_paise: int = Field(ge=0)
    emi_amount_paise: int = Field(ge=0)
    tenure_months: int = Field(ge=1, le=600)
    installments_paid: int = Field(ge=0, default=0)
    is_active: bool = True
    notes: str | None = Field(default=None, max_length=2000)
    loan_type: str | None = Field(default=None, max_length=200)
    creation_date: str | None = Field(default=None, max_length=32)
    finish_date: str | None = Field(default=None, max_length=32)
    principal_paise: int | None = Field(default=None, ge=0)
    outstanding_instalment_paise: int | None = Field(default=None, ge=0)


class CreditCardEmiPutBody(BaseModel):
    description: str | None = Field(default=None, min_length=1, max_length=500)
    limit_blocked_paise: int | None = Field(default=None, ge=0)
    emi_amount_paise: int | None = Field(default=None, ge=0)
    tenure_months: int | None = Field(default=None, ge=1, le=600)
    installments_paid: int | None = Field(default=None, ge=0)
    is_active: bool | None = None
    notes: str | None = Field(default=None, max_length=2000)
    loan_type: str | None = Field(default=None, max_length=200)
    creation_date: str | None = Field(default=None, max_length=32)
    finish_date: str | None = Field(default=None, max_length=32)
    principal_paise: int | None = Field(default=None, ge=0)
    outstanding_instalment_paise: int | None = Field(default=None, ge=0)
