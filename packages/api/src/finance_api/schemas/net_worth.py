"""Net worth API schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class NetWorthSnapshotOut(BaseModel):
    id: int
    snapshot_date: str
    total_assets_paise: int
    total_liabilities_paise: int
    net_worth_paise: int


class NetWorthSnapshotPost(BaseModel):
    """Insert or replace a snapshot for snapshot_date."""

    snapshot_date: str | None = Field(
        default=None,
        description="YYYY-MM-DD; defaults to today (server local date)",
    )
    computed_from_holdings: bool = Field(
        default=True,
        description="If true, assets = portfolio MV + fixed income principal; "
        "liabilities = active debt balances.",
    )
    total_assets_paise: int | None = Field(
        default=None,
        description="Required when computed_from_holdings is false.",
    )
    total_liabilities_paise: int | None = Field(
        default=None,
        description="Required when computed_from_holdings is false.",
    )
