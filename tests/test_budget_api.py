"""Budget API tests."""

from __future__ import annotations

from datetime import date
from urllib.parse import quote

from starlette.testclient import TestClient

from finance_api.main import create_app
from finance_api.services.budget_service import _row_status


def test_budget_row_status_exact_cap_is_full_not_over() -> None:
    assert _row_status(4_150_000, 4_150_000) == (1.0, "full")
    assert _row_status(100, 100) == (1.0, "full")
    assert _row_status(100, 74) == (0.74, "ok")
    assert _row_status(100, 75) == (0.75, "warn")
    assert _row_status(100, 101) == (1.01, "over")


def test_budget_vs_actual_empty() -> None:
    app = create_app()
    with TestClient(app) as client:
        r = client.get("/api/budget/vs-actual")
        assert r.status_code == 200
        data = r.json()
        assert "rows" in data
        assert "month" in data
        assert data["month"] == f"{date.today().year:04d}-{date.today().month:02d}"


def test_put_budget_round_trip() -> None:
    app = create_app()
    with TestClient(app) as client:
        cat = "Food Delivery"
        r = client.put(
            f"/api/budget/category/{quote(cat, safe='')}",
            json={"monthly_amount_paise": 50_000},
        )
        assert r.status_code == 200
        row = r.json()
        assert row["category"] == cat
        assert row["monthly_amount_paise"] == 50_000

        cur = client.get("/api/budget/current")
        assert cur.status_code == 200
        names = {b["category"] for b in cur.json()["budgets"]}
        assert cat in names


def test_rename_budget_category() -> None:
    app = create_app()
    with TestClient(app) as client:
        old = "Rename Test Cat"
        new = "Renamed Category Final"
        r = client.put(
            f"/api/budget/category/{quote(old, safe='')}",
            json={"monthly_amount_paise": 10_000},
        )
        assert r.status_code == 200

        r2 = client.post(
            "/api/budget/rename-category",
            json={"old_category": old, "new_category": new},
        )
        assert r2.status_code == 204

        cur = client.get("/api/budget/current")
        assert cur.status_code == 200
        names = {b["category"] for b in cur.json()["budgets"]}
        assert old not in names
        assert new in names
