"""Persistence operations for in-app alert notifications."""

from __future__ import annotations

from typing import cast

import aiosqlite

from finance_common.alerts.models import AlertNotification, AlertSeverity, AlertStatus

_NOTIFICATION_COLUMNS = """
    id, event_id, event_type, fingerprint, kind, title, message,
    severity, status, created_at, acked_at
"""


def _notification_from_row(row: tuple[object, ...]) -> AlertNotification:
    return AlertNotification(
        id=int(row[0]),
        event_id=int(row[1]) if row[1] is not None else None,
        event_type=str(row[2]),
        fingerprint=str(row[3]),
        kind=str(row[4]),
        title=str(row[5]),
        message=str(row[6]),
        severity=cast(AlertSeverity, str(row[7])),
        status=cast(AlertStatus, str(row[8])),
        created_at=str(row[9]),
        acked_at=str(row[10]) if row[10] is not None else None,
    )


async def insert_notification(
    conn: aiosqlite.Connection,
    *,
    event_id: int | None,
    event_type: str,
    fingerprint: str,
    kind: str,
    title: str,
    message: str,
    severity: str,
) -> int | None:
    """Insert a notification; return None when fingerprint already exists."""
    cursor = await conn.execute(
        """
        INSERT OR IGNORE INTO alert_notifications (
            event_id, event_type, fingerprint, kind, title, message, severity
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (event_id, event_type, fingerprint, kind, title, message, severity),
    )
    await conn.commit()
    if cursor.rowcount == 0 or cursor.lastrowid is None:
        return None
    return int(cursor.lastrowid)


async def list_notifications(
    conn: aiosqlite.Connection,
    *,
    status: str | None,
    limit: int = 100,
) -> list[AlertNotification]:
    """List notifications, optionally filtered by status."""
    if status is None:
        cursor = await conn.execute(
            f"""
            SELECT {_NOTIFICATION_COLUMNS}
            FROM alert_notifications
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
    else:
        cursor = await conn.execute(
            f"""
            SELECT {_NOTIFICATION_COLUMNS}
            FROM alert_notifications
            WHERE status = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (status, limit),
        )
    rows = await cursor.fetchall()
    return [_notification_from_row(row) for row in rows]


async def ack_notification(conn: aiosqlite.Connection, notification_id: int) -> bool:
    """Mark a notification as acknowledged; return False if already acked or missing."""
    cursor = await conn.execute(
        """
        UPDATE alert_notifications
        SET status = 'acked', acked_at = datetime('now')
        WHERE id = ? AND status = 'unread'
        """,
        (notification_id,),
    )
    await conn.commit()
    return cursor.rowcount > 0
