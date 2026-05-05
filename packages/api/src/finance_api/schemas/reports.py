"""Reports API schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FYMonthSpendingRow(BaseModel):
    fy_month: int = Field(ge=1, le=12, description="1=Apr … 12=Mar")
    label: str
    start_date: str
    end_date: str
    spent_paise: int


class FYSpendingReport(BaseModel):
    fy: str
    rows: list[FYMonthSpendingRow]
    total_spent_paise: int


class FYSummaryReport(BaseModel):
    fy: str
    total_spent_paise: int
    total_monthly_income_run_rate_paise: int = Field(
        description="Sum of active income streams normalized to monthly equivalent × 12 "
        "(rough FY income proxy).",
    )
    implied_savings_paise: int = Field(
        description="run_rate_annual − spending (informational).",
    )
