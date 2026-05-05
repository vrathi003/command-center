"""API smoke tests."""

from __future__ import annotations

from starlette.testclient import TestClient


def test_health(api_client: TestClient) -> None:
    r = api_client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_dashboard_summary(api_client: TestClient) -> None:
    r = api_client.get("/api/dashboard/summary")
    assert r.status_code == 200
    data = r.json()
    assert "current_fy" in data
    assert "spent_month_paise" in data
