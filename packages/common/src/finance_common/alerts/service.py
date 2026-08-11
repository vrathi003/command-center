"""Poll domain event outbox and persist in-app alert notifications."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping

import aiosqlite

from finance_common.alerts.route import route_event
from finance_common.project_config import load_project_config
from finance_common.repositories import alerts, domain_events

logger = logging.getLogger(__name__)


def _coerce_payload(raw: object) -> Mapping[str, object]:
    if isinstance(raw, dict):
        return raw
    return {}


async def poll_once(conn: aiosqlite.Connection, *, limit: int = 100) -> int:
    """Drain unprocessed domain events into alert notifications.

    Returns the number of events marked processed.
    """
    cfg = await load_project_config(conn)
    events = await domain_events.list_unprocessed(conn, limit=limit)
    processed_count = 0

    for event in events:
        try:
            payload = _coerce_payload(json.loads(event.payload_json))
            routed = route_event(event.event_type, payload, event_id=event.id)
            if routed is None:
                await domain_events.mark_processed(conn, event.id)
                processed_count += 1
                continue

            if not cfg.alerts_in_app_enabled:
                await domain_events.mark_processed(conn, event.id)
                processed_count += 1
                continue

            await alerts.insert_notification(
                conn,
                event_id=event.id,
                event_type=event.event_type,
                fingerprint=routed.fingerprint,
                kind=routed.kind,
                title=routed.title,
                message=routed.message,
                severity=routed.severity,
            )
            await domain_events.mark_processed(conn, event.id)
            processed_count += 1
        except Exception:
            logger.exception("Failed to process domain event %s", event.id)
            continue

    return processed_count
