"""Dashboard API."""

from __future__ import annotations

from typing import Annotated

import aiosqlite
from fastapi import APIRouter, Depends

from finance_api.deps import get_conn
from finance_api.schemas.dashboard import AlertItem, DashboardAlerts, DashboardSummary
from finance_api.services.dashboard_service import build_summary
from finance_common.repositories import alerts

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
    rows = await alerts.list_notifications(conn, status="unread")
    return DashboardAlerts(
        alerts=[
            AlertItem(
                id=row.id,
                kind=row.title or row.kind,
                message=row.message,
                severity=row.severity,
            )
            for row in rows
        ]
    )
