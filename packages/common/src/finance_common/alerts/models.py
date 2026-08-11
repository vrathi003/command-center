"""Value objects for in-app alert notifications."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AlertSeverity = Literal["info", "warn", "error"]
AlertStatus = Literal["unread", "acked"]


@dataclass(frozen=True, slots=True)
class AlertNotification:
    """Persisted in-app alert notification."""

    id: int
    event_id: int | None
    event_type: str
    fingerprint: str
    kind: str
    title: str
    message: str
    severity: AlertSeverity
    status: AlertStatus
    created_at: str
    acked_at: str | None
