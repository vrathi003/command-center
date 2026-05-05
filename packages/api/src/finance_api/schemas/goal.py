"""Goal schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GoalOut(BaseModel):
    id: int
    name: str
    category: str | None
    target_amount_paise: int
    current_amount_paise: int
    monthly_contribution_paise: int | None
    target_date: str | None
    progress_pct: float | None = Field(
        default=None,
        description="0–100 when target > 0, else null.",
    )


class GoalCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: str | None = None
    target_amount_paise: int = Field(ge=0)
    current_amount_paise: int = Field(default=0, ge=0)
    monthly_contribution_paise: int | None = Field(default=None, ge=0)
    target_date: str | None = None


class GoalPut(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: str | None = None
    target_amount_paise: int = Field(ge=0)
    current_amount_paise: int = Field(ge=0)
    monthly_contribution_paise: int | None = Field(default=None, ge=0)
    target_date: str | None = None
