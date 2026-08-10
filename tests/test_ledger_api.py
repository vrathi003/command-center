"""HTTP tests for the double-entry ledger API."""

from __future__ import annotations

import os
import sqlite3

from starlette.testclient import TestClient


def _seed_accounts() -> dict[str, int]:
    conn = sqlite3.connect(os.environ["DB_PATH"])
    accounts = [
        ("Bank", "savings", "asset_cash"),
        ("Bank 2", "savings", "asset_cash"),
        ("Expense", "expense", "expense"),
        ("Income", "income", "income"),
        ("Card", "credit_card", "liability_cc"),
        ("Investment", "investment", "asset_investment"),
    ]
    conn.executemany(
        "INSERT INTO accounts (name, type, account_class) VALUES (?, ?, ?)",
        accounts,
    )
    conn.commit()
    rows = conn.execute(
        "SELECT id, name FROM accounts WHERE name IN (?, ?, ?, ?, ?, ?)",
        tuple(account[0] for account in accounts),
    ).fetchall()
    conn.close()
    return {name: account_id for account_id, name in rows}


def test_create_get_balance_and_void_bank_expense(api_client: TestClient) -> None:
    ids = _seed_accounts()
    response = api_client.post(
        "/api/ledger/transactions",
        json={
            "date": "2026-08-01",
            "pattern": "bank_expense",
            "amount_paise": 50_000,
            "bank_account_id": ids["Bank"],
            "expense_account_id": ids["Expense"],
            "category": "Food Delivery",
            "payee": "Swiggy",
        },
    )

    assert response.status_code == 201
    transaction_id = response.json()["id"]
    transaction = api_client.get(f"/api/ledger/transactions/{transaction_id}")
    assert transaction.status_code == 200
    assert transaction.json()["status"] == "posted"
    assert transaction.json()["postings"] == [
        {
            "id": 1,
            "account_id": ids["Expense"],
            "amount_paise": 50_000,
            "category": "Food Delivery",
        },
        {
            "id": 2,
            "account_id": ids["Bank"],
            "amount_paise": -50_000,
            "category": None,
        },
    ]

    balance = api_client.get(f"/api/ledger/accounts/{ids['Bank']}/balance")
    assert balance.status_code == 200
    assert balance.json() == {"account_id": ids["Bank"], "balance_paise": -50_000}

    void_response = api_client.post(f"/api/ledger/transactions/{transaction_id}/void")
    assert void_response.status_code == 200
    assert void_response.json()["status"] == "void"
    assert api_client.get(f"/api/ledger/accounts/{ids['Bank']}/balance").json() == {
        "account_id": ids["Bank"],
        "balance_paise": 0,
    }


def test_create_all_pattern_types(api_client: TestClient) -> None:
    ids = _seed_accounts()
    bodies = [
        {
            "pattern": "bank_expense",
            "bank_account_id": ids["Bank"],
            "expense_account_id": ids["Expense"],
            "category": "Food",
        },
        {
            "pattern": "bank_income",
            "bank_account_id": ids["Bank"],
            "income_account_id": ids["Income"],
            "category": "Salary",
        },
        {
            "pattern": "transfer",
            "from_account_id": ids["Bank"],
            "to_account_id": ids["Bank 2"],
        },
        {
            "pattern": "cc_swipe",
            "cc_account_id": ids["Card"],
            "expense_account_id": ids["Expense"],
            "category": "Shopping",
        },
        {
            "pattern": "cc_bill_pay",
            "bank_account_id": ids["Bank"],
            "cc_account_id": ids["Card"],
        },
        {
            "pattern": "investment_buy",
            "bank_account_id": ids["Bank"],
            "investment_account_id": ids["Investment"],
        },
        {
            "pattern": "custom",
            "postings": [
                {"account_id": ids["Expense"], "amount_paise": 10_000, "category": "Other"},
                {"account_id": ids["Bank"], "amount_paise": -10_000},
            ],
        },
    ]

    for body in bodies:
        response = api_client.post(
            "/api/ledger/transactions",
            json={"date": "2026-08-01", "amount_paise": 10_000, **body},
        )
        assert response.status_code == 201, response.text


def test_month_summary_uses_cash_accounts_and_posted_transactions(api_client: TestClient) -> None:
    ids = _seed_accounts()
    income = api_client.post(
        "/api/ledger/transactions",
        json={
            "date": "2026-08-01",
            "pattern": "bank_income",
            "amount_paise": 100_000,
            "bank_account_id": ids["Bank"],
            "income_account_id": ids["Income"],
            "category": "Salary",
        },
    )
    assert income.status_code == 201
    expense = api_client.post(
        "/api/ledger/transactions",
        json={
            "date": "2026-08-02",
            "pattern": "bank_expense",
            "amount_paise": 25_000,
            "bank_account_id": ids["Bank"],
            "expense_account_id": ids["Expense"],
            "category": "Food",
        },
    )
    assert expense.status_code == 201
    investment = api_client.post(
        "/api/ledger/transactions",
        json={
            "date": "2026-08-03",
            "pattern": "investment_buy",
            "amount_paise": 40_000,
            "bank_account_id": ids["Bank"],
            "investment_account_id": ids["Investment"],
        },
    )
    assert investment.status_code == 201

    response = api_client.get("/api/ledger/summary/month?year=2026&month=8")

    assert response.status_code == 200
    assert response.json() == {
        "budget_spend_month_paise": 25_000,
        "cash_out_month_paise": 65_000,
        "cash_in_month_paise": 100_000,
        "net_worth_paise": 75_000,
        "budget_spend_by_category": {"Food": 25_000},
    }


def test_month_summary_net_worth_is_as_of_requested_month(api_client: TestClient) -> None:
    ids = _seed_accounts()
    for posted_date, amount_paise in (("2026-01-15", 100_000), ("2026-08-15", 50_000)):
        response = api_client.post(
            "/api/ledger/transactions",
            json={
                "date": posted_date,
                "pattern": "bank_income",
                "amount_paise": amount_paise,
                "bank_account_id": ids["Bank"],
                "income_account_id": ids["Income"],
                "category": "Salary",
            },
        )
        assert response.status_code == 201, response.text

    response = api_client.get("/api/ledger/summary/month?year=2026&month=1")

    assert response.status_code == 200
    assert response.json()["net_worth_paise"] == 100_000


def test_accounts_api_assigns_and_accepts_account_class(api_client: TestClient) -> None:
    credit_card = api_client.post(
        "/api/accounts/",
        json={"name": "Visa", "type": "credit_card"},
    )
    assert credit_card.status_code == 201, credit_card.text
    assert credit_card.json()["account_class"] == "liability_cc"

    custom = api_client.post(
        "/api/accounts/",
        json={
            "name": "Brokerage",
            "type": "other",
            "account_class": "asset_investment",
        },
    )
    assert custom.status_code == 201, custom.text
    assert custom.json()["account_class"] == "asset_investment"

    updated = api_client.put(
        f"/api/accounts/{custom.json()['id']}",
        json={
            "name": "Brokerage",
            "type": "loan",
            "account_class": "liability_cc",
            "is_active": True,
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["account_class"] == "liability_cc"

    listed = api_client.get("/api/accounts/")
    assert listed.status_code == 200
    assert (
        next(item for item in listed.json() if item["id"] == credit_card.json()["id"])[
            "account_class"
        ]
        == "liability_cc"
    )


def test_accounts_api_preserves_custom_account_class_when_update_omits_it(
    api_client: TestClient,
) -> None:
    created = api_client.post(
        "/api/accounts/",
        json={
            "name": "Brokerage",
            "type": "other",
            "account_class": "asset_investment",
        },
    )
    assert created.status_code == 201, created.text

    updated = api_client.put(
        f"/api/accounts/{created.json()['id']}",
        json={"name": "Renamed Brokerage", "type": "other"},
    )

    assert updated.status_code == 200, updated.text
    assert updated.json()["account_class"] == "asset_investment"


def test_accounts_api_rejects_unknown_account_class(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/accounts/",
        json={"name": "Invalid", "type": "other", "account_class": "banana"},
    )

    assert response.status_code == 422
