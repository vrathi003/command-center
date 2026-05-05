"""Net worth API tests."""

from __future__ import annotations

from starlette.testclient import TestClient


def test_net_worth_history_empty(api_client: TestClient) -> None:
    r = api_client.get("/api/net-worth/history")
    assert r.status_code == 200
    assert r.json() == []


def test_net_worth_snapshot_computed(api_client: TestClient) -> None:
    r = api_client.post("/api/net-worth/snapshot", json={"computed_from_holdings": True})
    assert r.status_code == 201
    body = r.json()
    assert "snapshot_date" in body
    assert body["total_assets_paise"] == 0
    assert body["total_liabilities_paise"] == 0
    assert body["net_worth_paise"] == 0

    h = api_client.get("/api/net-worth/history")
    assert h.status_code == 200
    rows = h.json()
    assert len(rows) == 1


def test_net_worth_snapshot_manual(api_client: TestClient) -> None:
    r = api_client.post(
        "/api/net-worth/snapshot",
        json={
            "computed_from_holdings": False,
            "snapshot_date": "2025-01-15",
            "total_assets_paise": 100_000,
            "total_liabilities_paise": 20_000,
        },
    )
    assert r.status_code == 201
    assert r.json()["net_worth_paise"] == 80_000
