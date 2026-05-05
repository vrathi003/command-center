"""Pydantic schemas for dashboard endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DashboardSummary(BaseModel):
    """Payload for GET /api/dashboard/summary (Phase 1 — expandable)."""

    current_fy: str = Field(description="Active FY string, e.g. '2025-26'")
    spent_today_paise: int
    spent_week_paise: int
    spent_month_paise: int
    spent_by_category_month: dict[str, int]
    spent_by_account_month: dict[str, int]
    total_debt_paise: int
    net_worth_paise: int | None
    portfolio_value_paise: int
    monthly_income_paise: int | None = Field(
        default=None,
        description="Sum of active income streams as monthly run-rate (paise).",
    )
    savings_rate_month: float | None = Field(
        default=None,
        description="(monthly_income − spent_this_month) / monthly_income when income > 0.",
    )


class AlertItem(BaseModel):
    kind: str
    message: str
    severity: str = "info"


class DashboardAlerts(BaseModel):
    alerts: list[AlertItem]
