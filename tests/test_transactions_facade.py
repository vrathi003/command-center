"""Tests for the legacy transactions facade over posted ledger entries."""

from __future__ import annotations

import os
import sqlite3

from starlette.testclient import TestClient


def _seed_accounts() -> dict[str, int]:
    conn = sqlite3.connect(os.environ["DB_PATH"])
    accounts = [
        ("Bank", "savings", "asset_cash"),
        ("Bank 2", "savings", "asset_cash"),
        ("Card", "credit_card", "liability_cc"),
        ("Expense", "expense", "expense"),
        ("Income", "income", "income"),
    ]
    conn.executemany(
        "INSERT INTO accounts (name, type, account_class) VALUES (?, ?, ?)",
        accounts,
    )
    conn.commit()
    rows = conn.execute("SELECT id, name FROM accounts").fetchall()
    conn.close()
    return {name: account_id for account_id, name in rows}


def _mark_cutover() -> None:
    conn = sqlite3.connect(os.environ["DB_PATH"])
    conn.execute(
        """
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        ("project_config.migration.legacy_cutover_at", "2026-08-10T12:00:00+00:00"),
    )
    conn.commit()
    conn.close()


def _post(
    api_client: TestClient, body: dict[str, object]
) -> int:
    response = api_client.post("/api/ledger/transactions", json=body)
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def test_transactions_list_maps_ledger_debit_after_cutover(api_client: TestClient) -> None:
    ids = _seed_accounts()
    transaction_id = _post(
        api_client,
        {
            "date": "2026-08-01",
            "pattern": "bank_expense",
            "amount_paise": 50_000,
            "bank_account_id": ids["Bank"],
            "expense_account_id": ids["Expense"],
            "category": "Food",
            "payee": "Swiggy",
            "notes": "Dinner",
            "source": "import",
        },
    )
    _mark_cutover()

    response = api_client.get("/api/transactions/")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": transaction_id,
            "date": "2026-08-01",
            "amount_paise": 50_000,
            "category": "Food",
            "merchant": "Swiggy",
            "payment_mode": "Other",
            "account": "Bank",
            "notes": "Dinner",
            "transaction_type": "debit",
            "source": "import",
            "account_id": ids["Bank"],
            "transfer_pair_id": None,
            "tags": None,
        }
    ]


def test_transaction_get_maps_ledger_credit_after_cutover(api_client: TestClient) -> None:
    ids = _seed_accounts()
    transaction_id = _post(
        api_client,
        {
            "date": "2026-08-02",
            "pattern": "bank_income",
            "amount_paise": 125_000,
            "bank_account_id": ids["Bank"],
            "income_account_id": ids["Income"],
            "category": "Salary",
            "payee": "Employer",
        },
    )
    _mark_cutover()

    response = api_client.get(f"/api/transactions/{transaction_id}")

    assert response.status_code == 200
    assert response.json() == {
        "id": transaction_id,
        "date": "2026-08-02",
        "amount_paise": 125_000,
        "category": "Salary",
        "merchant": "Employer",
        "payment_mode": "Other",
        "account": "Bank",
        "notes": None,
        "transaction_type": "credit",
        "source": "manual",
        "account_id": ids["Bank"],
        "transfer_pair_id": None,
        "tags": None,
    }


def test_transactions_list_maps_ledger_transfer_after_cutover(api_client: TestClient) -> None:
    ids = _seed_accounts()
    transaction_id = _post(
        api_client,
        {
            "date": "2026-08-03",
            "pattern": "transfer",
            "amount_paise": 75_000,
            "from_account_id": ids["Bank"],
            "to_account_id": ids["Bank 2"],
            "payee": "Move money",
            "external_key": "transfer:1",
        },
    )
    _mark_cutover()

    response = api_client.get("/api/transactions/")

    assert response.status_code == 200
    row = response.json()[0]
    assert row["id"] == transaction_id
    assert row["amount_paise"] == 75_000
    assert row["category"] == "Other"
    assert row["transaction_type"] == "transfer"
    assert row["transfer_pair_id"] == "transfer:1"
    assert row["account_id"] == ids["Bank"]
    assert row["account"] == "Bank"
