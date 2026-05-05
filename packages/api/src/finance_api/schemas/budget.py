"""Budget API schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class BudgetCurrentRow(BaseModel):
    category: str
    monthly_amount_paise: int
    effective_from: str


class BudgetCurrentResponse(BaseModel):
    fy: str
    budgets: list[BudgetCurrentRow]


class BudgetVsActualRow(BaseModel):
    category: str
    budget_paise: int | None = Field(
        default=None,
        description="Null when no budget set for this category in the FY.",
    )
    spent_paise: int
    pct_of_budget: float | None = Field(
        default=None,
        description="spent/budget when budget > 0; else null.",
    )
    status: Literal["none", "ok", "warn", "over", "full"]


class BudgetVsActualResponse(BaseModel):
    fy: str
    month: str = Field(description="Calendar month as YYYY-MM")
    rows: list[BudgetVsActualRow]


class BudgetPutBody(BaseModel):
    monthly_amount_paise: int = Field(ge=0, description="Monthly cap in paise.")


class BudgetRenameBody(BaseModel):
    old_category: str = Field(min_length=1, description="Current category label.")
    new_category: str = Field(min_length=1, description="New category label.")


class BudgetHistoryRow(BaseModel):
    category: str
    monthly_amount_paise: int
    effective_from: str
    updated_at: str


class BudgetHistoryResponse(BaseModel):
    fy: str
    entries: list[BudgetHistoryRow]
