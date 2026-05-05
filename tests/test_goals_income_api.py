"""Goals, income, settings, reports API smoke tests."""

from __future__ import annotations

from starlette.testclient import TestClient


def test_goals_crud(api_client: TestClient) -> None:
    r = api_client.get("/api/goals/")
    assert r.status_code == 200
    assert r.json() == []

    r = api_client.post(
        "/api/goals/",
        json={
            "name": "Test goal",
            "category": None,
            "target_amount_paise": 100_000,
            "current_amount_paise": 0,
            "monthly_contribution_paise": 5_000,
            "target_date": None,
        },
    )
    assert r.status_code == 201
    gid = r.json()["id"]

    r = api_client.put(
        f"/api/goals/{gid}",
        json={
            "name": "Test goal",
            "category": "x",
            "target_amount_paise": 100_000,
            "current_amount_paise": 50_000,
            "monthly_contribution_paise": None,
            "target_date": None,
        },
    )
    assert r.status_code == 200
    assert r.json()["progress_pct"] == 50.0

    r = api_client.delete(f"/api/goals/{gid}")
    assert r.status_code == 204


def test_income_streams(api_client: TestClient) -> None:
    r = api_client.get("/api/income/summary")
    assert r.status_code == 200
    assert r.json()["stream_count"] == 0

    r = api_client.post(
        "/api/income/",
        json={
            "name": "Side gig",
            "type": "Freelance",
            "amount_paise": 3_000_000,
            "frequency": "monthly",
            "taxability": "fully_taxable",
        },
    )
    assert r.status_code == 201
    assert r.json()["monthly_equivalent_paise"] == 3_000_000

    r = api_client.get("/api/income/summary")
    assert r.json()["total_monthly_equivalent_paise"] == 3_000_000


def test_settings_patch(api_client: TestClient) -> None:
    r = api_client.get("/api/settings/")
    assert r.status_code == 200
    assert "current_fy" in r.json()

    r = api_client.put(
        "/api/settings/", json={"tax_regime": "old", "tax_80c_annual_paise": 15000000}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["tax_regime"] == "old"
    assert body["tax_80c_annual_paise"] == 15000000
    assert "tax_80d_annual_paise" in body


def test_reports_fy(api_client: TestClient) -> None:
    r = api_client.get("/api/reports/fy-spending")
    assert r.status_code == 200
    data = r.json()
    assert data["fy"]
    assert len(data["rows"]) == 12
    assert "total_spent_paise" in data

    r = api_client.get("/api/reports/fy-summary")
    assert r.status_code == 200
    assert r.json()["fy"]
