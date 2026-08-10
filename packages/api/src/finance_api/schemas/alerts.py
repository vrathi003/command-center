"""Pydantic schemas for alert notification endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class AlertNotificationResponse(BaseModel):
    id: int
    event_id: int | None
    event_type: str
    fingerprint: str
    kind: str
    title: str
    message: str
    severity: str
    status: str
    created_at: str
    acked_at: str | None = None
