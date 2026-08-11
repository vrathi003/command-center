"""Subscription record-charge ledger posting."""

from __future__ import annotations

import os
import sqlite3

from starlette.testclient import TestClient


def _create_bank_and_expense(api_client: TestClient) -> tuple[int, int]:
    bank = api_client.post(
        "/api/accounts/",
        json={"name": "HDFC Savings", "type": "savings", "account_class": "asset_cash"},
    )
    assert bank.status_code == 201, bank.text
    bank_id = int(bank.json()["id"])

    accounts = api_client.get("/api/accounts/")
    assert accounts.status_code == 200, accounts.text
    expense = next(
        a for a in accounts.json() if a["name"] == "Uncategorized Expense"
    )
    expense_id = int(expense["id"])
    return bank_id, expense_id


def _seed_bank_balance(api_client: TestClient, *, bank_id: int, amount_paise: int) -> None:
    accounts = api_client.get("/api/accounts/")
    assert accounts.status_code == 200, accounts.text
    equity = next(
        a for a in accounts.json() if a["name"] == "Opening Balance Equity"
    )
    equity_id = int(equity["id"])

    response = api_client.post(
        "/api/ledger/transactions",
        json={
            "pattern": "custom",
            "date": "2026-07-01",
            "postings": [
                {"account_id": bank_id, "amount_paise": amount_paise},
                {"account_id": equity_id, "amount_paise": -amount_paise},
            ],
            "source": "dashboard",
            "notes": "Seed bank",
        },
    )
    assert response.status_code == 201, response.text


def _create_subscription(
    api_client: TestClient,
    *,
    bank_id: int | None,
    next_billing_date: str = "2026-08-01",
    billing_cycle: str = "monthly",
    category: str | None = "Streaming",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "Netflix",
        "amount_paise": 649_00,
        "billing_cycle": billing_cycle,
        "next_billing_date": next_billing_date,
        "category": category,
    }
    if bank_id is not None:
        payload["account_id"] = bank_id

    response = api_client.post("/api/subscriptions/", json=payload)
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


def test_record_charge_bank_reduces_balance_and_advances_monthly(
    api_client: TestClient,
) -> None:
    bank_id, expense_id = _create_bank_and_expense(api_client)
    _seed_bank_balance(api_client, bank_id=bank_id, amount_paise=100_000_00)
    sub = _create_subscription(api_client, bank_id=bank_id)
    sub_id = int(sub["id"])

    legacy_before = _legacy_transaction_count()
    bank_before = _balance(api_client, bank_id)
    expense_before = _balance(api_client, expense_id)

    response = api_client.post(
        f"/api/subscriptions/{sub_id}/record-charge",
        json={"date": "2026-08-01"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    ledger_transaction_id = int(body["ledger_transaction_id"])
    assert ledger_transaction_id > 0
    assert body["next_billing_date"] == "2026-09-01"
    assert body["subscription"]["next_billing_date"] == "2026-09-01"

    conn = sqlite3.connect(os.environ["DB_PATH"])
    ledger_row = conn.execute(
        "SELECT source, payee FROM ledger_transactions WHERE id = ?",
        (ledger_transaction_id,),
    ).fetchone()
    category_posting = conn.execute(
        """
        SELECT category FROM ledger_postings
        WHERE transaction_id = ? AND category = 'Streaming'
        """,
        (ledger_transaction_id,),
    ).fetchone()
    conn.close()

    assert ledger_row == ("subscription", "Netflix")
    assert category_posting == ("Streaming",)
    assert _balance(api_client, bank_id) == bank_before - 649_00
    assert _balance(api_client, expense_id) == expense_before + 649_00
    assert _legacy_transaction_count() == legacy_before


def test_record_charge_cc_swipe_increases_liability(api_client: TestClient) -> None:
    bank_id, expense_id = _create_bank_and_expense(api_client)

    cc_account = api_client.post(
        "/api/accounts/",
        json={
            "name": "Ledger Visa",
            "type": "credit_card",
            "account_class": "liability_cc",
        },
    )
    assert cc_account.status_code == 201, cc_account.text
    cc_account_id = int(cc_account.json()["id"])

    sub = _create_subscription(api_client, bank_id=cc_account_id, category=None)
    sub_id = int(sub["id"])

    cc_before = _balance(api_client, cc_account_id)
    expense_before = _balance(api_client, expense_id)

    response = api_client.post(
        f"/api/subscriptions/{sub_id}/record-charge",
        json={"date": "2026-08-15"},
    )

    assert response.status_code == 201, response.text
    ledger_transaction_id = int(response.json()["ledger_transaction_id"])

    conn = sqlite3.connect(os.environ["DB_PATH"])
    category_posting = conn.execute(
        """
        SELECT category FROM ledger_postings
        WHERE transaction_id = ? AND category = 'Subscriptions'
        """,
        (ledger_transaction_id,),
    ).fetchone()
    conn.close()

    assert category_posting == ("Subscriptions",)
    assert _balance(api_client, cc_account_id) == cc_before - 649_00
    assert _balance(api_client, expense_id) == expense_before + 649_00
    assert response.json()["next_billing_date"] == "2026-09-15"


def test_record_charge_missing_account_returns_422(api_client: TestClient) -> None:
    sub = _create_subscription(api_client, bank_id=None)
    sub_id = int(sub["id"])

    response = api_client.post(
        f"/api/subscriptions/{sub_id}/record-charge",
        json={"date": "2026-08-01"},
    )

    assert response.status_code == 422
    assert "account_id required" in response.json()["detail"]


def test_record_charge_requires_double_entry(api_client: TestClient) -> None:
    bank_id, _ = _create_bank_and_expense(api_client)
    sub = _create_subscription(api_client, bank_id=bank_id)
    sub_id = int(sub["id"])

    api_client.put(
        "/api/settings/",
        json={"project_config": {"ledger_engine": "legacy"}},
    )

    response = api_client.post(
        f"/api/subscriptions/{sub_id}/record-charge",
        json={"date": "2026-08-01"},
    )

    assert response.status_code == 422
    assert "double_entry" in response.json()["detail"]
