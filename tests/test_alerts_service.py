from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from finance_common.alerts.route import route_event
from finance_common.alerts.service import poll_once
from finance_common.db import ensure_database
from finance_common.project_config import (
    KEY_ALERTS_IN_APP_ENABLED,
    ProjectConfig,
    save_project_config,
)
from finance_common.repositories import alerts, domain_events
from finance_common.repositories.settings_repo import set_value


@pytest.mark.parametrize(
    ("event_type", "payload", "expected_fingerprint", "expected_severity"),
    [
        (
            "budget.threshold",
            {
                "ym": "2026-08",
                "category": "Food",
                "status": "warn",
                "spent_paise": 800000,
                "budget_paise": 1000000,
                "pct": 80,
            },
            "budget|2026-08|Food|warn",
            "warn",
        ),
        (
            "budget.threshold",
            {
                "ym": "2026-08",
                "category": "Food",
                "status": "over",
                "spent_paise": 1100000,
                "budget_paise": 1000000,
                "pct": 110,
            },
            "budget|2026-08|Food|over",
            "error",
        ),
        (
            "debt.emi_due",
            {"debt_id": 3, "name": "Home loan", "due_date": "2026-08-15", "days_until": 2},
            "emi|3|2026-08-15",
            "warn",
        ),
        (
            "credit_card.due",
            {"card_id": 7, "name": "HDFC Regalia", "due_date": "2026-08-20", "when": "tomorrow"},
            "cc_due|7|2026-08-20",
            "warn",
        ),
        (
            "intake.quarantine_created",
            {"candidate_id": 42, "reason": "possible_duplicate"},
            "intake.quarantine|42",
            "warn",
        ),
        (
            "intake.candidate_approved",
            {"candidate_id": 11},
            "intake.approved|11",
            "info",
        ),
        (
            "intake.candidate_rejected",
            {"candidate_id": 12, "reason": "duplicate"},
            "intake.rejected|12",
            "info",
        ),
        (
            "digest.weekly",
            {"label": "2026-08-11", "message": "FY spend to date: ₹100.00"},
            "digest|weekly|2026-08-11",
            "info",
        ),
        (
            "digest.monthly",
            {"label": "2026-07", "message": "Total spend: ₹50.00"},
            "digest|monthly|2026-07",
            "info",
        ),
        (
            "ops.job_failed",
            {"job": "price_sync", "error": "Yahoo timeout"},
            "ops.job_failed|price_sync|Yahoo timeout",
            "error",
        ),
        (
            "ops.gmail_auth_failed",
            {"error": "invalid_grant: Bad Request"},
            "ops.gmail_auth_failed",
            "error",
        ),
        (
            "ops.backup_failed",
            {"error": "No space left on device"},
            "ops.backup_failed|No space left on device",
            "error",
        ),
        (
            "migration.quarantine_created",
            {"candidate_id": 99, "reason": "needs_opening_balance"},
            "migration.quarantine|99",
            "warn",
        ),
    ],
)
def test_route_event_known_types(
    event_type: str,
    payload: dict[str, object],
    expected_fingerprint: str,
    expected_severity: str,
) -> None:
    routed = route_event(event_type, payload, event_id=1)
    assert routed is not None
    assert routed.fingerprint == expected_fingerprint
    assert routed.severity == expected_severity
    assert routed.title
    assert routed.message


def test_route_event_budget_pct_formats_as_integer_percent() -> None:
    routed = route_event(
        "budget.threshold",
        {
            "ym": "2026-08",
            "category": "Food",
            "status": "warn",
            "spent_paise": 800000,
            "budget_paise": 1000000,
            "pct": 80,
        },
        event_id=1,
    )
    assert routed is not None
    assert "80% utilized" in routed.message


def test_route_event_budget_pct_float_rounds_for_display() -> None:
    routed = route_event(
        "budget.threshold",
        {
            "ym": "2026-08",
            "category": "Food",
            "status": "warn",
            "pct": 80.4,
        },
        event_id=1,
    )
    assert routed is not None
    assert "80% utilized" in routed.message


def test_route_event_unknown_returns_none() -> None:
    assert route_event("recon.period_closed", {"statement_id": 1}, event_id=5) is None


def test_route_event_missing_keys_uses_event_fingerprint_fallback() -> None:
    routed = route_event("budget.threshold", {"category": "Food"}, event_id=77)
    assert routed is not None
    assert routed.fingerprint == "budget.threshold|77"


@pytest.mark.asyncio
async def test_poll_once_creates_notification_for_known_event(tmp_path: Path) -> None:
    db = tmp_path / "alerts_service.db"
    await ensure_database(db)

    async with aiosqlite.connect(db) as conn:
        event_id = await domain_events.append_event(
            conn,
            event_type="budget.threshold",
            payload={
                "ym": "2026-08",
                "category": "Food",
                "status": "warn",
                "spent_paise": 800000,
                "budget_paise": 1000000,
                "pct": 80,
            },
        )

        processed = await poll_once(conn)
        assert processed == 1
        assert await domain_events.list_unprocessed(conn) == []

        rows = await alerts.list_notifications(conn, status="unread")
        assert len(rows) == 1
        assert rows[0].event_id == event_id
        assert rows[0].event_type == "budget.threshold"
        assert rows[0].fingerprint == "budget|2026-08|Food|warn"
        assert rows[0].kind == "budget"
        assert rows[0].severity == "warn"
        assert "Food" in rows[0].title


@pytest.mark.asyncio
async def test_poll_once_unknown_event_processed_without_notification(tmp_path: Path) -> None:
    db = tmp_path / "alerts_service.db"
    await ensure_database(db)

    async with aiosqlite.connect(db) as conn:
        await domain_events.append_event(
            conn,
            event_type="recon.period_closed",
            payload={"statement_id": 1},
        )

        processed = await poll_once(conn)
        assert processed == 1
        assert await domain_events.list_unprocessed(conn) == []
        assert await alerts.list_notifications(conn, status=None) == []


@pytest.mark.asyncio
async def test_poll_once_duplicate_fingerprint_one_row_two_events_processed(
    tmp_path: Path,
) -> None:
    db = tmp_path / "alerts_service.db"
    await ensure_database(db)

    payload = {
        "debt_id": 1,
        "name": "Car loan",
        "due_date": "2026-08-15",
        "days_until": 3,
    }

    async with aiosqlite.connect(db) as conn:
        await domain_events.append_event(conn, event_type="debt.emi_due", payload=payload)
        await domain_events.append_event(conn, event_type="debt.emi_due", payload=payload)

        processed = await poll_once(conn)
        assert processed == 2
        assert await domain_events.list_unprocessed(conn) == []
        assert len(await alerts.list_notifications(conn, status=None)) == 1


@pytest.mark.asyncio
async def test_poll_once_alerts_disabled_marks_processed_without_rows(tmp_path: Path) -> None:
    db = tmp_path / "alerts_service.db"
    await ensure_database(db)

    async with aiosqlite.connect(db) as conn:
        await set_value(conn, KEY_ALERTS_IN_APP_ENABLED, "false")
        await domain_events.append_event(
            conn,
            event_type="credit_card.due",
            payload={
                "card_id": 2,
                "name": "ICICI Amazon Pay",
                "due_date": "2026-08-21",
                "when": "today",
            },
        )

        processed = await poll_once(conn)
        assert processed == 1
        assert await domain_events.list_unprocessed(conn) == []
        assert await alerts.list_notifications(conn, status=None) == []


@pytest.mark.asyncio
async def test_poll_once_respects_alerts_enabled_toggle(tmp_path: Path) -> None:
    db = tmp_path / "alerts_service.db"
    await ensure_database(db)

    async with aiosqlite.connect(db) as conn:
        await save_project_config(conn, ProjectConfig(alerts_in_app_enabled=False))
        await domain_events.append_event(
            conn,
            event_type="intake.candidate_approved",
            payload={"candidate_id": 5},
        )
        assert await poll_once(conn) == 1
        assert await alerts.list_notifications(conn, status=None) == []

        await save_project_config(conn, ProjectConfig(alerts_in_app_enabled=True))
        await domain_events.append_event(
            conn,
            event_type="intake.candidate_approved",
            payload={"candidate_id": 6},
        )
        assert await poll_once(conn) == 1
        rows = await alerts.list_notifications(conn, status=None)
        assert len(rows) == 1
        assert rows[0].fingerprint == "intake.approved|6"
