"""Debt loan accounts and record-emi ledger posting."""

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

    expense = api_client.post(
        "/api/accounts/",
        json={"name": "Uncategorized Expense", "type": "expense", "account_class": "expense"},
    )
    assert expense.status_code == 201, expense.text
    expense_id = int(expense.json()["id"])
    return bank_id, expense_id


def _create_debt(
    api_client: TestClient,
    *,
    bank_id: int,
    next_emi_date: str = "2026-07-03",
) -> dict[str, object]:
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
            "next_emi_date": next_emi_date,
            "tenure_months": 60,
            "payment_account_id": bank_id,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _seed_loan_opening_balance(
    api_client: TestClient,
    *,
    bank_id: int,
    loan_account_id: int,
    amount_paise: int,
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


def test_create_debt_links_loan_account_in_double_entry(api_client: TestClient) -> None:
    bank_id, _ = _create_bank_and_expense(api_client)
    debt = _create_debt(api_client, bank_id=bank_id)

    assert debt["account_id"] is not None
    assert debt["payment_account_id"] == bank_id

    accounts = api_client.get("/api/accounts/")
    assert accounts.status_code == 200
    loan_accounts = [
        a for a in accounts.json() if a["id"] == debt["account_id"]
    ]
    assert len(loan_accounts) == 1
    assert loan_accounts[0]["type"] == "loan"
    assert loan_accounts[0]["account_class"] == "liability_loan"
    assert loan_accounts[0]["name"] == "Car Loan"


def test_record_emi_posts_through_ledger(api_client: TestClient) -> None:
    bank_id, _ = _create_bank_and_expense(api_client)
    debt = _create_debt(api_client, bank_id=bank_id)
    loan_account_id = int(debt["account_id"])
    debt_id = int(debt["id"])

    _seed_loan_opening_balance(
        api_client,
        bank_id=bank_id,
        loan_account_id=loan_account_id,
        amount_paise=900_000_00,
    )
    legacy_before = _legacy_transaction_count()
    bank_before = _balance(api_client, bank_id)

    response = api_client.post(
        f"/api/debt/{debt_id}/record-emi",
        json={
            "date": "2026-07-03",
            "principal_paise": 13_500_00,
            "interest_paise": 6_500_00,
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert "ledger_transaction_id" in body
    ledger_transaction_id = int(body["ledger_transaction_id"])
    assert ledger_transaction_id > 0

    conn = sqlite3.connect(os.environ["DB_PATH"])
    ledger_row = conn.execute(
        "SELECT source, payee FROM ledger_transactions WHERE id = ?",
        (ledger_transaction_id,),
    ).fetchone()
    interest_posting = conn.execute(
        """
        SELECT category FROM ledger_postings
        WHERE transaction_id = ? AND category = 'Debt Interest'
        """,
        (ledger_transaction_id,),
    ).fetchone()
    debt_row = conn.execute(
        "SELECT current_balance_paise, next_emi_date FROM debts WHERE id = ?",
        (debt_id,),
    ).fetchone()
    conn.close()

    assert ledger_row == ("dashboard", "Car Loan")
    assert interest_posting == ("Debt Interest",)

    assert _balance(api_client, bank_id) == bank_before - 20_000_00
    loan_balance = _balance(api_client, loan_account_id)
    assert loan_balance == -886_500_00
    assert max(0, -loan_balance) == 886_500_00
    assert _legacy_transaction_count() == legacy_before

    assert debt_row == (886_500_00, "2026-08-03")


def test_record_emi_defaults_split_from_amortization(api_client: TestClient) -> None:
    bank_id, _ = _create_bank_and_expense(api_client)
    debt = _create_debt(api_client, bank_id=bank_id, next_emi_date="2025-01-03")
    loan_account_id = int(debt["account_id"])
    debt_id = int(debt["id"])

    _seed_loan_opening_balance(
        api_client,
        bank_id=bank_id,
        loan_account_id=loan_account_id,
        amount_paise=1_000_000_00,
    )
    bank_before = _balance(api_client, bank_id)

    amort = api_client.get(f"/api/debt/{debt_id}/amortization")
    assert amort.status_code == 200
    first_row = amort.json()["rows"][0]

    response = api_client.post(
        f"/api/debt/{debt_id}/record-emi",
        json={"date": "2025-01-03"},
    )

    assert response.status_code == 201, response.text
    assert int(response.json()["ledger_transaction_id"]) > 0
    assert _balance(api_client, bank_id) == bank_before - first_row["payment_paise"]


def test_record_emi_returns_503_when_ledger_writes_disabled(api_client: TestClient) -> None:
    bank_id, _ = _create_bank_and_expense(api_client)
    debt = _create_debt(api_client, bank_id=bank_id)
    debt_id = int(debt["id"])

    api_client.app.state.ledger_writes_enabled = False
    response = api_client.post(
        f"/api/debt/{debt_id}/record-emi",
        json={"date": "2026-07-03", "principal_paise": 10_000_00, "interest_paise": 5_000_00},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Ledger writes disabled due to integrity failure"
