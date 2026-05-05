"""Dashboard API."""

from __future__ import annotations

from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends

from finance_api.deps import get_conn
from finance_api.schemas.dashboard import DashboardAlerts, DashboardSummary
from finance_api.services.dashboard_service import build_summary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
async def dashboard_summary(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> DashboardSummary:
    return await build_summary(conn)


@router.get("/alerts", response_model=DashboardAlerts)
async def dashboard_alerts(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> DashboardAlerts:
    _ = conn
    return DashboardAlerts(alerts=[])
