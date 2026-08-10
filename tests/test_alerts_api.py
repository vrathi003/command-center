"""HTTP tests for in-app alert notifications."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from finance_api.main import create_app
from finance_common.alerts.service import poll_once
from finance_common.db import ensure_database, open_db
from finance_common.repositories import alerts, domain_events


async def _seed_budget_alert(db_path: Path) -> int:
    await ensure_database(db_path)
    async with open_db(db_path) as conn:
        await domain_events.append_event(
            conn,
            event_type="budget.threshold",
            payload={
                "ym": "2026-08",
                "category": "Food",
                "status": "warn",
                "spent_paise": 800_000,
                "budget_paise": 1_000_000,
                "pct": 80,
            },
        )
        await poll_once(conn)
        rows = await alerts.list_notifications(conn, status="unread")
        assert len(rows) == 1
        return rows[0].id


@pytest.fixture
def alert_client(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, int]]:
    db = tmp_path_factory.mktemp("alerts_api") / "test.db"
    monkeypatch.setenv("DB_PATH", str(db))
    alert_id = asyncio.run(_seed_budget_alert(db))
    with TestClient(create_app()) as client:
        yield client, alert_id


def test_list_alerts_default_unread(alert_client: tuple[TestClient, int]) -> None:
    client, alert_id = alert_client
    r = client.get("/api/alerts")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["id"] == alert_id
    assert data[0]["status"] == "unread"
    assert data[0]["kind"] == "budget"


def test_list_alerts_status_filters(alert_client: tuple[TestClient, int]) -> None:
    client, alert_id = alert_client
    r_all = client.get("/api/alerts", params={"status": "all"})
    assert r_all.status_code == 200
    assert len(r_all.json()) == 1

    r_acked = client.get("/api/alerts", params={"status": "acked"})
    assert r_acked.status_code == 200
    assert r_acked.json() == []

    ack = client.post(f"/api/alerts/{alert_id}/ack")
    assert ack.status_code == 200
    assert ack.json()["status"] == "acked"

    r_unread = client.get("/api/alerts", params={"status": "unread"})
    assert r_unread.status_code == 200
    assert r_unread.json() == []

    r_acked2 = client.get("/api/alerts", params={"status": "acked"})
    assert r_acked2.status_code == 200
    assert len(r_acked2.json()) == 1


def test_ack_alert_404_when_missing(api_client: TestClient) -> None:
    r = api_client.post("/api/alerts/99999/ack")
    assert r.status_code == 404


def test_dashboard_alerts_unread(alert_client: tuple[TestClient, int]) -> None:
    client, alert_id = alert_client
    r = client.get("/api/dashboard/alerts")
    assert r.status_code == 200
    data = r.json()
    assert len(data["alerts"]) == 1
    item = data["alerts"][0]
    assert item["id"] == alert_id
    assert "Budget warning" in item["kind"]
    assert item["message"]
    assert item["severity"] == "warn"

    client.post(f"/api/alerts/{alert_id}/ack")
    r2 = client.get("/api/dashboard/alerts")
    assert r2.status_code == 200
    assert r2.json()["alerts"] == []


def test_lifespan_poll_once_drains_outbox(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = tmp_path_factory.mktemp("lifespan") / "test.db"
    monkeypatch.setenv("DB_PATH", str(db))

    async def _append_only() -> None:
        await ensure_database(db)
        async with open_db(db) as conn:
            await domain_events.append_event(
                conn,
                event_type="budget.threshold",
                payload={
                    "ym": "2026-08",
                    "category": "Transport",
                    "status": "over",
                    "spent_paise": 120_000,
                    "budget_paise": 100_000,
                    "pct": 120,
                },
            )

    asyncio.run(_append_only())

    with TestClient(create_app()) as client:
        r = client.get("/api/alerts")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["kind"] == "budget"
