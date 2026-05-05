"""Pydantic schemas for the Insurance module."""

from __future__ import annotations

from pydantic import BaseModel, Field


class InsurancePolicyOut(BaseModel):
    id: int
    name: str
    type: str
    provider: str | None
    policy_number: str | None
    sum_insured_paise: int | None
    premium_paise: int
    premium_frequency: str
    start_date: str | None
    end_date: str | None
    renewal_date: str | None
    policyholder: str
    covered_members: str | None
    asset_id: int | None
    tax_deduction_section: str | None
    status: str
    notes: str | None
    # Derived
    annual_premium_paise: int


class InsurancePolicyCreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: str = Field(min_length=1, max_length=50)
    provider: str | None = None
    policy_number: str | None = None
    sum_insured_paise: int | None = Field(default=None, ge=0)
    premium_paise: int = Field(ge=0)
    premium_frequency: str = "annual"
    start_date: str | None = None
    end_date: str | None = None
    renewal_date: str | None = None
    policyholder: str = "Self"
    covered_members: str | None = None
    asset_id: int | None = None
    tax_deduction_section: str | None = None
    status: str = "active"
    notes: str | None = None


class InsurancePolicyUpdateBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    type: str | None = None
    provider: str | None = None
    policy_number: str | None = None
    sum_insured_paise: int | None = Field(default=None, ge=0)
    premium_paise: int | None = Field(default=None, ge=0)
    premium_frequency: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    renewal_date: str | None = None
    policyholder: str | None = None
    covered_members: str | None = None
    asset_id: int | None = None
    tax_deduction_section: str | None = None
    status: str | None = None
    notes: str | None = None


class InsurancePremiumOut(BaseModel):
    id: int
    policy_id: int
    payment_date: str
    amount_paise: int
    period_start: str | None
    period_end: str | None
    payment_mode: str | None
    reference_number: str | None
    notes: str | None


class InsurancePremiumBody(BaseModel):
    payment_date: str
    amount_paise: int = Field(ge=0)
    period_start: str | None = None
    period_end: str | None = None
    payment_mode: str | None = None
    reference_number: str | None = None
    notes: str | None = None


class InsuranceSummaryOut(BaseModel):
    active_policy_count: int
    total_annual_premium_paise: int
    renewing_within_60_days: int
    total_80d_self_paise: int
    total_80d_parents_paise: int
    total_80c_paise: int
