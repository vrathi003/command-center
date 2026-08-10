"""Value objects for domain event outbox rows and alert notifications."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AlertSeverity = Literal["info", "warn", "error"]
AlertStatus = Literal["unread", "acked"]


@dataclass(frozen=True, slots=True)
class DomainEventRow:
    """Persisted domain event awaiting or after outbox processing."""

    id: int
    event_type: str
    payload_json: str
    created_at: str
    processed_at: str | None


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
