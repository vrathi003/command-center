"""Debt API tests."""

from __future__ import annotations

from starlette.testclient import TestClient

from finance_api.main import create_app


def test_debt_summary_and_list() -> None:
    app = create_app()
    with TestClient(app) as client:
        s = client.get("/api/debt/summary")
        assert s.status_code == 200
        data = s.json()
        assert "total_outstanding_paise" in data
        assert "active_count" in data

        lst = client.get("/api/debt/")
        assert lst.status_code == 200
        assert isinstance(lst.json(), list)
