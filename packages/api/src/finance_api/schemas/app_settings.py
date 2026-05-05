"""App settings (FY, tax hints) exposed via API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SettingsOut(BaseModel):
    current_fy: str
    tax_regime: str | None = Field(
        default=None,
        description="India income tax: 'old' or 'new' (optional).",
    )
    tax_80c_annual_paise: int | None = Field(
        default=None,
        description="Declared Section 80C investments (annual, paise).",
    )
    tax_80d_annual_paise: int | None = Field(
        default=None,
        description="Declared Section 80D health insurance (annual, paise).",
    )


class SettingsPatch(BaseModel):
    current_fy: str | None = Field(default=None, description="Must match YYYY-YY")
    tax_regime: str | None = Field(default=None, description="old | new")
    tax_80c_annual_paise: int | None = Field(default=None, ge=0)
    tax_80d_annual_paise: int | None = Field(default=None, ge=0)
