"""Income record-income ledger posting and W3 fields (W3)."""

from __future__ import annotations

import os
import sqlite3

from starlette.testclient import TestClient


def _create_bank(api_client: TestClient) -> int:
    bank = api_client.post(
        "/api/accounts/",
        json={"name": "HDFC Savings", "type": "savings", "account_class": "asset_cash"},
    )
    assert bank.status_code == 201, bank.text
    return int(bank.json()["id"])


def _income_account_id(api_client: TestClient) -> int:
    accounts = api_client.get("/api/accounts/")
    assert accounts.status_code == 200, accounts.text
    income = next(
        a for a in accounts.json() if a["name"] == "Uncategorized Income"
    )
    return int(income["id"])


def _create_income_stream(
    api_client: TestClient,
    *,
    bank_id: int | None,
    amount_paise: int = 150_000_00,
    category: str | None = "Salary",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "Primary salary",
        "type": "salary",
        "amount_paise": amount_paise,
        "frequency": "monthly",
        "taxability": "fully_taxable",
        "category": category,
    }
    if bank_id is not None:
        payload["default_account_id"] = bank_id

    response = api_client.post("/api/income/", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _balance(api_client: TestClient, account_id: int) -> int:
    response = api_client.get(f"/api/ledger/accounts/{account_id}/balance")
    assert response.status_code == 200, response.text
    return int(response.json()["balance_paise"])


def _legacy_transaction_count() -> int:
    conn = sqlite3.connect(os.environ["DB_PATH"])
    count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()
    conn.close()
    assert count is not None
    return int(count[0])


def test_income_crud_includes_default_account_and_category(
    api_client: TestClient,
) -> None:
    bank_id = _create_bank(api_client)
    created = _create_income_stream(api_client, bank_id=bank_id, category="Freelance")
    income_id = int(created["id"])

    assert created["default_account_id"] == bank_id
    assert created["category"] == "Freelance"

    updated = api_client.put(
        f"/api/income/{income_id}",
        json={
            "name": "Consulting",
            "type": "freelance",
            "amount_paise": 80_000_00,
            "frequency": "monthly",
            "taxability": "fully_taxable",
            "is_active": True,
            "default_account_id": bank_id,
            "category": "Consulting",
        },
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["category"] == "Consulting"
    assert body["default_account_id"] == bank_id


def test_record_income_credits_bank_and_income_accounts(
    api_client: TestClient,
) -> None:
    bank_id = _create_bank(api_client)
    income_acct_id = _income_account_id(api_client)
    stream = _create_income_stream(api_client, bank_id=bank_id)
    income_id = int(stream["id"])

    legacy_before = _legacy_transaction_count()
    bank_before = _balance(api_client, bank_id)
    income_before = _balance(api_client, income_acct_id)

    response = api_client.post(
        f"/api/income/{income_id}/record-income",
        json={"date": "2026-08-01"},
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["ledger_transaction_id"] > 0
    assert data["income"]["id"] == income_id

    assert _legacy_transaction_count() == legacy_before
    assert _balance(api_client, bank_id) == bank_before + 150_000_00
    assert _balance(api_client, income_acct_id) == income_before - 150_000_00


def test_record_income_uses_stream_category_and_amount_override(
    api_client: TestClient,
) -> None:
    bank_id = _create_bank(api_client)
    stream = _create_income_stream(
        api_client, bank_id=bank_id, amount_paise=100_000_00, category="Rental"
    )
    income_id = int(stream["id"])

    response = api_client.post(
        f"/api/income/{income_id}/record-income",
        json={
            "date": "2026-08-05",
            "amount_paise": 25_000_00,
            "category": "Rent received",
        },
    )
    assert response.status_code == 201, response.text
    assert _balance(api_client, bank_id) == 25_000_00


def test_record_income_defaults_category_to_salary(
    api_client: TestClient,
) -> None:
    bank_id = _create_bank(api_client)
    created = api_client.post(
        "/api/income/",
        json={
            "name": "Side gig",
            "type": "freelance",
            "amount_paise": 10_000_00,
            "frequency": "monthly",
            "taxability": "fully_taxable",
            "default_account_id": bank_id,
        },
    )
    assert created.status_code == 201, created.text
    income_id = int(created.json()["id"])

    response = api_client.post(
        f"/api/income/{income_id}/record-income",
        json={"date": "2026-08-10"},
    )
    assert response.status_code == 201, response.text


def test_record_income_missing_account_returns_422(api_client: TestClient) -> None:
    stream = _create_income_stream(api_client, bank_id=None)
    income_id = int(stream["id"])

    response = api_client.post(
        f"/api/income/{income_id}/record-income",
        json={"date": "2026-08-01"},
    )
    assert response.status_code == 422
    assert "account_id" in response.json()["detail"]


def test_record_income_requires_double_entry(api_client: TestClient) -> None:
    bank_id = _create_bank(api_client)
    stream = _create_income_stream(api_client, bank_id=bank_id)
    income_id = int(stream["id"])

    settings = api_client.put(
        "/api/settings/",
        json={"project_config": {"ledger_engine": "legacy"}},
    )
    assert settings.status_code == 200, settings.text

    response = api_client.post(
        f"/api/income/{income_id}/record-income",
        json={"date": "2026-08-01"},
    )
    assert response.status_code == 422
    assert "double_entry" in response.json()["detail"]
