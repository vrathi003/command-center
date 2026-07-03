"""Statement import API tests."""

from __future__ import annotations

from starlette.testclient import TestClient


def test_statement_import_rules_crud(api_client: TestClient) -> None:
    create = api_client.post(
        "/api/statement-import/rules",
        json={
            "bank": "ICICI",
            "card": "Test Card",
            "from_emails": ["credit_cards@icici.bank.in"],
            "subject_contains": "statement",
            "pdf_password": "secret",
            "is_enabled": True,
        },
    )
    assert create.status_code == 201, create.text
    rule = create.json()
    assert rule["bank"] == "ICICI"
    rid = rule["id"]

    listed = api_client.get("/api/statement-import/rules")
    assert listed.status_code == 200
    assert any(r["id"] == rid for r in listed.json())

    updated = api_client.put(
        f"/api/statement-import/rules/{rid}",
        json={
            "bank": "ICICI",
            "card": "Updated Card",
            "from_emails": ["credit_cards@icici.bank.in"],
            "subject_contains": "statement",
            "pdf_password": "secret",
            "is_enabled": False,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["card"] == "Updated Card"
    assert updated.json()["is_enabled"] is False

    deleted = api_client.delete(f"/api/statement-import/rules/{rid}")
    assert deleted.status_code == 204


def test_statement_import_tags_put(api_client: TestClient) -> None:
    res = api_client.put(
        "/api/statement-import/tags",
        json={
            "tags": [
                {"tag_name": "UBER", "regex_patterns": ["uber"], "is_enabled": True},
                {"tag_name": "FOOD", "regex_patterns": ["zomato"], "is_enabled": True},
            ]
        },
    )
    assert res.status_code == 200
    tags = res.json()
    assert len(tags) == 2
    names = {t["tag_name"] for t in tags}
    assert names == {"UBER", "FOOD"}


def test_statement_import_gmail_status(api_client: TestClient) -> None:
    res = api_client.get("/api/statement-import/gmail-status")
    assert res.status_code == 200
    body = res.json()
    assert "configured" in body


def test_statement_import_latest_csv_404_when_empty(api_client: TestClient) -> None:
    res = api_client.get("/api/statement-import/snapshots/latest/csv")
    assert res.status_code == 404
