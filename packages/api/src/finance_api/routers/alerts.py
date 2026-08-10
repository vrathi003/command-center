"""HTTP API for in-app alert notifications."""

from __future__ import annotations

from typing import Annotated, Literal

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query

from finance_api.deps import get_conn
from finance_api.schemas.alerts import AlertNotificationResponse
from finance_common.alerts.models import AlertNotification
from finance_common.repositories import alerts

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _notification_response(row: AlertNotification) -> AlertNotificationResponse:
    return AlertNotificationResponse(
        id=row.id,
        event_id=row.event_id,
        event_type=row.event_type,
        fingerprint=row.fingerprint,
        kind=row.kind,
        title=row.title,
        message=row.message,
        severity=row.severity,
        status=row.status,
        created_at=row.created_at,
        acked_at=row.acked_at,
    )


@router.get("", response_model=list[AlertNotificationResponse])
async def list_alerts(
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
    status: Literal["unread", "acked", "all"] = Query(default="unread"),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AlertNotificationResponse]:
    repo_status = None if status == "all" else status
    rows = await alerts.list_notifications(conn, status=repo_status, limit=limit)
    return [_notification_response(row) for row in rows]


@router.post("/{notification_id}/ack", response_model=AlertNotificationResponse)
async def ack_alert(
    notification_id: int,
    conn: Annotated[aiosqlite.Connection, Depends(get_conn)],
) -> AlertNotificationResponse:
    ok = await alerts.ack_notification(conn, notification_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Notification not found or already acked")
    rows = await alerts.list_notifications(conn, status="acked", limit=500)
    row = next((item for item in rows if item.id == notification_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return _notification_response(row)
