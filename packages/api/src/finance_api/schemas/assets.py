"""Pydantic schemas for the Assets module."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ── Asset master ───────────────────────────────────────────────────────────────


class AssetOut(BaseModel):
    id: int
    name: str
    type: str
    status: str
    purchase_date: str | None
    purchase_price_paise: int | None
    current_value_paise: int | None
    ownership_percent: float
    co_owner: str | None
    notes: str | None


class AssetCreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: str = Field(min_length=1, max_length=50)
    status: str = "active"
    purchase_date: str | None = None
    purchase_price_paise: int | None = Field(default=None, ge=0)
    current_value_paise: int | None = Field(default=None, ge=0)
    ownership_percent: float = Field(default=100.0, ge=0.0, le=100.0)
    co_owner: str | None = None
    notes: str | None = None


class AssetUpdateBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    type: str | None = None
    status: str | None = None
    purchase_date: str | None = None
    purchase_price_paise: int | None = Field(default=None, ge=0)
    current_value_paise: int | None = Field(default=None, ge=0)
    ownership_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    co_owner: str | None = None
    notes: str | None = None


# ── Real estate detail ─────────────────────────────────────────────────────────


class RealEstateOut(BaseModel):
    asset_id: int
    address: str | None
    city: str | None
    state: str | None
    pin_code: str | None
    builder: str | None
    project_name: str | None
    unit_details: str | None
    carpet_area_sqft: float | None
    builtin_area_sqft: float | None
    super_builtin_area_sqft: float | None
    purchase_psf_paise: int | None
    current_psf_paise: int | None
    psf_area_type: str
    possession_status: str
    possession_date_estimated: str | None
    possession_date_actual: str | None
    agreement_value_paise: int | None
    circle_rate_psf_paise: int | None


class RealEstateBody(BaseModel):
    address: str | None = None
    city: str | None = None
    state: str | None = None
    pin_code: str | None = None
    builder: str | None = None
    project_name: str | None = None
    unit_details: str | None = None
    carpet_area_sqft: float | None = Field(default=None, ge=0)
    builtin_area_sqft: float | None = Field(default=None, ge=0)
    super_builtin_area_sqft: float | None = Field(default=None, ge=0)
    purchase_psf_paise: int | None = Field(default=None, ge=0)
    current_psf_paise: int | None = Field(default=None, ge=0)
    psf_area_type: str = "super_builtin"
    possession_status: str = "under_construction"
    possession_date_estimated: str | None = None
    possession_date_actual: str | None = None
    agreement_value_paise: int | None = Field(default=None, ge=0)
    circle_rate_psf_paise: int | None = Field(default=None, ge=0)


# ── Vehicle detail ─────────────────────────────────────────────────────────────


class VehicleOut(BaseModel):
    asset_id: int
    make: str | None
    model: str | None
    variant: str | None
    year: int | None
    registration_number: str | None
    fuel_type: str | None
    color: str | None
    depreciation_rate_percent: float


class VehicleBody(BaseModel):
    make: str | None = None
    model: str | None = None
    variant: str | None = None
    year: int | None = Field(default=None, ge=1900, le=2100)
    registration_number: str | None = None
    fuel_type: str | None = None
    color: str | None = None
    depreciation_rate_percent: float = Field(default=15.0, ge=0.0, le=100.0)


# ── Asset costs ────────────────────────────────────────────────────────────────


class AssetCostOut(BaseModel):
    id: int
    asset_id: int
    cost_type: str
    description: str | None
    amount_paise: int
    paid_date: str | None
    is_paid: bool


class AssetCostBody(BaseModel):
    cost_type: str = Field(min_length=1, max_length=50)
    description: str | None = None
    amount_paise: int = Field(ge=0)
    paid_date: str | None = None
    is_paid: bool = True


# ── Asset loan linkages ────────────────────────────────────────────────────────


class AssetLoanOut(BaseModel):
    id: int
    asset_id: int
    debt_id: int
    debt_name: str
    sanctioned_amount_paise: int | None
    disbursed_amount_paise: int | None
    pre_emi_paise: int | None
    final_emi_paise: int | None
    notes: str | None
    # Derived
    remaining_to_disburse_paise: int | None


class AssetLoanBody(BaseModel):
    debt_id: int
    sanctioned_amount_paise: int | None = Field(default=None, ge=0)
    disbursed_amount_paise: int | None = Field(default=None, ge=0)
    pre_emi_paise: int | None = Field(default=None, ge=0)
    final_emi_paise: int | None = Field(default=None, ge=0)
    notes: str | None = None


# ── Asset payments ─────────────────────────────────────────────────────────────


class AssetPaymentOut(BaseModel):
    id: int
    asset_id: int
    amount_paise: int
    """Total milestone amount (cash + loan)."""
    amount_cash_paise: int
    amount_loan_paise: int
    milestone: str | None
    payment_mode: str | None
    reference_number: str | None
    receipt_number: str | None
    receipt_date: str | None
    notes: str | None
    is_paid: bool
    due_date: str | None
    paid_date: str | None
    fund_source: Literal["cash", "bank_loan"]
    payment_date: str
    """Effective date for sorting (paid_date, else due_date, else legacy column)."""


class AssetPaymentBody(BaseModel):
    amount_cash_paise: int = Field(default=0, ge=0)
    amount_loan_paise: int = Field(default=0, ge=0)
    amount_paise: int | None = Field(default=None, ge=0)
    """Legacy: if cash and loan are both zero, total is split using fund_source."""
    milestone: str | None = None
    payment_mode: str | None = None
    reference_number: str | None = None
    receipt_number: str | None = None
    receipt_date: str | None = None
    notes: str | None = None
    is_paid: bool = True
    due_date: str | None = None
    paid_date: str | None = None
    fund_source: Literal["cash", "bank_loan"] = "cash"
    payment_date: str | None = None
    """Legacy: when is_paid, treated as paid_date if paid_date is omitted."""


# ── Asset detail (aggregated) ──────────────────────────────────────────────────


class AssetDetailOut(BaseModel):
    asset: AssetOut
    real_estate: RealEstateOut | None
    vehicle: VehicleOut | None
    costs: list[AssetCostOut]
    loans: list[AssetLoanOut]
    payments: list[AssetPaymentOut]
    # Derived totals (total_cost_paise = cost breakdown + payment milestones)
    total_cost_paise: int
    total_paid_paise: int
    total_payment_milestones_upcoming_paise: int
    appreciation_pct: float | None


class AssetSummaryOut(BaseModel):
    total_assets: int
    total_current_value_paise: int
    total_purchase_price_paise: int
