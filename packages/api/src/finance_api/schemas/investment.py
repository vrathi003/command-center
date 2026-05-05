"""Investment holdings API schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class InvestmentOut(BaseModel):
    id: int
    instrument: str
    type: str
    isin_code: str | None
    units: float | None
    avg_price_paise: int | None
    current_price_paise: int | None
    last_synced: str | None
    sector: str | None = None
    equity_tax_class: str = "unspecified"
    cost_basis_paise: int | None = Field(
        default=None,
        description="units × avg_price when both set.",
    )
    market_value_paise: int | None = Field(
        default=None,
        description="units × current_price when both set.",
    )
    unrealized_paise: int | None = None


class PortfolioSummaryOut(BaseModel):
    cost_basis_paise: int
    market_value_paise: int
    unrealized_paise: int
    holdings_count: int


class InvestmentPutBody(BaseModel):
    instrument: str | None = None
    type: str | None = None
    isin_code: str | None = None
    units: float | None = None
    avg_price_paise: int | None = None
    current_price_paise: int | None = None
    last_synced: str | None = None
    sector: str | None = None
    equity_tax_class: str | None = None


class InvestmentCreateBody(BaseModel):
    instrument: str
    type: str
    isin_code: str | None = None
    units: float | None = None
    avg_price_paise: int | None = None
    current_price_paise: int | None = None
    sector: str | None = None
    equity_tax_class: str | None = None


class FixedIncomeOut(BaseModel):
    id: int
    institution: str
    type: str
    principal_paise: int
    rate_percent: float | None
    start_date: str | None
    maturity_date: str | None


class FixedIncomeSummaryOut(BaseModel):
    total_principal_paise: int
    instrument_count: int


class FixedIncomeCreateBody(BaseModel):
    institution: str = Field(min_length=1, max_length=200)
    type: str = Field(min_length=1, max_length=80)
    principal_paise: int = Field(ge=0)
    rate_percent: float | None = None
    start_date: str | None = None
    maturity_date: str | None = None


class FixedIncomePutBody(BaseModel):
    institution: str | None = None
    type: str | None = None
    principal_paise: int | None = Field(default=None, ge=0)
    rate_percent: float | None = None
    start_date: str | None = None
    maturity_date: str | None = None
