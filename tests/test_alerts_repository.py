from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from finance_common.db import ensure_database
from finance_common.repositories import alerts, domain_events


@pytest.mark.asyncio
async def test_domain_event_outbox_drain_lifecycle(tmp_path: Path) -> None:
    db = tmp_path / "alerts_repo.db"
    await ensure_database(db)

    async with aiosqlite.connect(db) as conn:
        event_id = await domain_events.append_event(
            conn,
            event_type="budget.threshold",
            payload={"category": "Food", "status": "warn"},
        )

        unprocessed = await domain_events.list_unprocessed(conn)
        assert len(unprocessed) == 1
        assert unprocessed[0].id == event_id
        assert unprocessed[0].event_type == "budget.threshold"
        assert unprocessed[0].processed_at is None
        assert "Food" in unprocessed[0].payload_json

        await domain_events.mark_processed(conn, event_id, when="2026-08-11T00:00:00")
        assert await domain_events.list_unprocessed(conn) == []

        cursor = await conn.execute(
            "SELECT processed_at FROM domain_events WHERE id = ?",
            (event_id,),
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == "2026-08-11T00:00:00"


@pytest.mark.asyncio
async def test_alert_notification_insert_list_and_ack(tmp_path: Path) -> None:
    db = tmp_path / "alerts_repo.db"
    await ensure_database(db)

    async with aiosqlite.connect(db) as conn:
        event_id = await domain_events.append_event(
            conn,
            event_type="budget.threshold",
            payload={"category": "Food"},
        )

        notification_id = await alerts.insert_notification(
            conn,
            event_id=event_id,
            event_type="budget.threshold",
            fingerprint="budget|2026-08|Food|warn",
            kind="budget",
            title="Budget warning",
            message="Food is at 80%",
            severity="warn",
        )
        assert notification_id is not None

        unread = await alerts.list_notifications(conn, status="unread")
        assert len(unread) == 1
        assert unread[0].id == notification_id
        assert unread[0].event_id == event_id
        assert unread[0].fingerprint == "budget|2026-08|Food|warn"
        assert unread[0].status == "unread"
        assert unread[0].acked_at is None

        fetched = await alerts.get_notification(conn, notification_id)
        assert fetched is not None
        assert fetched.id == notification_id
        assert fetched.status == "unread"

        assert await alerts.get_notification(conn, 99999) is None

        assert await alerts.ack_notification(conn, notification_id) is True
        assert await alerts.ack_notification(conn, notification_id) is False

        acked = await alerts.list_notifications(conn, status="acked")
        assert len(acked) == 1
        assert acked[0].status == "acked"
        assert acked[0].acked_at is not None
        assert await alerts.list_notifications(conn, status="unread") == []


@pytest.mark.asyncio
async def test_insert_notification_duplicate_fingerprint_returns_none(tmp_path: Path) -> None:
    db = tmp_path / "alerts_repo.db"
    await ensure_database(db)

    async with aiosqlite.connect(db) as conn:
        event_id = await domain_events.append_event(
            conn,
            event_type="debt.emi_due",
            payload={"debt_id": 1},
        )

        first_id = await alerts.insert_notification(
            conn,
            event_id=event_id,
            event_type="debt.emi_due",
            fingerprint="emi|1|2026-08-15",
            kind="emi",
            title="EMI due",
            message="Loan payment due in 3 days",
            severity="warn",
        )
        assert first_id is not None

        second_id = await alerts.insert_notification(
            conn,
            event_id=event_id,
            event_type="debt.emi_due",
            fingerprint="emi|1|2026-08-15",
            kind="emi",
            title="EMI due again",
            message="Duplicate should be ignored",
            severity="warn",
        )
        assert second_id is None
        assert len(await alerts.list_notifications(conn, status=None)) == 1
