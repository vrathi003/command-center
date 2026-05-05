"""Investment & fixed-income API tests."""

from __future__ import annotations

from starlette.testclient import TestClient

from finance_api.main import create_app


def test_portfolio_summary() -> None:
    app = create_app()
    with TestClient(app) as client:
        r = client.get("/api/investments/portfolio-summary")
        assert r.status_code == 200
        data = r.json()
        assert "cost_basis_paise" in data
        assert "market_value_paise" in data


def test_list_investments() -> None:
    app = create_app()
    with TestClient(app) as client:
        r = client.get("/api/investments/")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


def test_fixed_income_list() -> None:
    app = create_app()
    with TestClient(app) as client:
        r = client.get("/api/fixed-income/summary")
        assert r.status_code == 200
        lst = client.get("/api/fixed-income/")
        assert lst.status_code == 200
