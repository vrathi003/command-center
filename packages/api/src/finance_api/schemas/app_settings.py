"""App settings (FY, tax hints) exposed via API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ProjectConfigOut(BaseModel):
    discord_enabled: bool
    discord_alerts_enabled: bool
    alerts_in_app_enabled: bool
    ledger_engine: Literal["legacy", "double_entry"]
    intake_auto_post_min_confidence: float
    intake_duplicate_date_window_days: int
    recon_match_date_window_days: int
    legacy_cutover_at: str | None
    legacy_archive: bool


class ProjectConfigPatch(BaseModel):
    discord_enabled: bool | None = None
    discord_alerts_enabled: bool | None = None
    alerts_in_app_enabled: bool | None = None
    ledger_engine: Literal["legacy", "double_entry"] | None = None
    intake_auto_post_min_confidence: float | None = None
    intake_duplicate_date_window_days: int | None = None
    recon_match_date_window_days: int | None = None


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
    project_config: ProjectConfigOut


class SettingsPatch(BaseModel):
    current_fy: str | None = Field(default=None, description="Must match YYYY-YY")
    tax_regime: str | None = Field(default=None, description="old | new")
    tax_80c_annual_paise: int | None = Field(default=None, ge=0)
    tax_80d_annual_paise: int | None = Field(default=None, ge=0)
    project_config: ProjectConfigPatch | None = None
