"""Debt list/summary use live liability_loan outstanding under double_entry."""

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


def _create_debt(api_client: TestClient, bank_id: int) -> dict[str, object]:
    response = api_client.post(
        "/api/debt/",
        json={
            "name": "Car Loan",
            "lender": "HDFC",
            "type": "Car Loan",
            "original_amount_paise": 1_000_000_00,
            "current_balance_paise": 900_000_00,
            "emi_paise": 20_000_00,
            "rate_percent": 9.0,
            "start_date": "2025-01-03",
            "first_emi_date": "2025-01-03",
            "next_emi_date": "2026-09-03",
            "tenure_months": 60,
            "payment_account_id": bank_id,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _seed_loan_opening(
    api_client: TestClient, *, bank_id: int, loan_account_id: int, amount_paise: int
) -> None:
    response = api_client.post(
        "/api/ledger/transactions",
        json={
            "pattern": "custom",
            "date": "2025-01-01",
            "postings": [
                {"account_id": bank_id, "amount_paise": amount_paise},
                {"account_id": loan_account_id, "amount_paise": -amount_paise},
            ],
            "source": "dashboard",
            "notes": "Loan disbursal",
        },
    )
    assert response.status_code == 201, response.text


def test_list_and_summary_use_ledger_when_cache_stale(api_client: TestClient) -> None:
    bank_id = _create_bank(api_client)
    debt = _create_debt(api_client, bank_id)
    loan_id = int(debt["account_id"])
    _seed_loan_opening(
        api_client, bank_id=bank_id, loan_account_id=loan_id, amount_paise=800_000_00
    )

    conn = sqlite3.connect(os.environ["DB_PATH"])
    conn.execute(
        "UPDATE debts SET current_balance_paise = ? WHERE id = ?",
        (123_456_00, int(debt["id"])),
    )
    conn.commit()
    conn.close()

    detail = api_client.get(f"/api/debt/{debt['id']}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["current_balance_paise"] == 800_000_00

    listing = api_client.get("/api/debt/")
    assert listing.status_code == 200
    row = next(d for d in listing.json() if d["id"] == debt["id"])
    assert row["current_balance_paise"] == 800_000_00

    summary = api_client.get("/api/debt/summary")
    assert summary.status_code == 200
    assert summary.json()["total_outstanding_paise"] == 800_000_00

    dash = api_client.get("/api/dashboard/summary")
    assert dash.status_code == 200
    assert dash.json()["total_debt_paise"] == 800_000_00


def test_without_ledger_activity_keeps_cached_balance(api_client: TestClient) -> None:
    bank_id = _create_bank(api_client)
    debt = _create_debt(api_client, bank_id)
    detail = api_client.get(f"/api/debt/{debt['id']}")
    assert detail.status_code == 200
    assert detail.json()["current_balance_paise"] == 900_000_00
