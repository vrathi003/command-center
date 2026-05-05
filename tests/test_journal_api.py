"""Journal API tests."""

from __future__ import annotations

from datetime import date

from starlette.testclient import TestClient


def test_journal_get_missing(api_client: TestClient) -> None:
    r = api_client.get("/api/journal/2020-01-15")
    assert r.status_code == 404


def test_journal_put_get_round_trip(api_client: TestClient) -> None:
    r = api_client.put(
        "/api/journal/2020-01-15",
        json={"body": "  # Hello\n\nworld  "},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["entry_date"] == "2020-01-15"
    assert data["body"] == "# Hello\n\nworld"

    r = api_client.get("/api/journal/2020-01-15")
    assert r.status_code == 200
    assert r.json()["body"] == "# Hello\n\nworld"


def test_journal_put_empty_deletes(api_client: TestClient) -> None:
    api_client.put("/api/journal/2020-02-01", json={"body": "x"})
    r = api_client.put("/api/journal/2020-02-01", json={"body": "   "})
    assert r.status_code == 204
    r = api_client.get("/api/journal/2020-02-01")
    assert r.status_code == 404


def test_journal_put_empty_idempotent(api_client: TestClient) -> None:
    r = api_client.put("/api/journal/2030-03-03", json={"body": ""})
    assert r.status_code == 204
    r = api_client.get("/api/journal/2030-03-03")
    assert r.status_code == 404


def test_journal_invalid_date(api_client: TestClient) -> None:
    r = api_client.get("/api/journal/not-a-date")
    assert r.status_code == 422


def test_journal_list_default_range(api_client: TestClient) -> None:
    d = date.today().isoformat()
    r = api_client.put(f"/api/journal/{d}", json={"body": "today entry"})
    assert r.status_code == 200
    r = api_client.get("/api/journal/")
    assert r.status_code == 200
    dates = [row["entry_date"] for row in r.json()]
    assert d in dates


def test_journal_list_range(api_client: TestClient) -> None:
    api_client.put("/api/journal/2019-01-01", json={"body": "a"})
    api_client.put("/api/journal/2019-01-31", json={"body": "b"})
    r = api_client.get("/api/journal/?from=2019-01-01&to=2019-01-31")
    assert r.status_code == 200
    dates = sorted(row["entry_date"] for row in r.json())
    assert dates == ["2019-01-01", "2019-01-31"]


def test_journal_list_from_only_rejected(api_client: TestClient) -> None:
    r = api_client.get("/api/journal/?from=2019-01-01")
    assert r.status_code == 422


def test_journal_list_bad_range(api_client: TestClient) -> None:
    r = api_client.get("/api/journal/?from=2019-02-01&to=2019-01-01")
    assert r.status_code == 422
