"""Dashboard / budget / FY reports use ledger budget-spend lenses when double_entry."""

from __future__ import annotations

from datetime import date

from starlette.testclient import TestClient

from finance_common.fy import date_to_fy


def _bank(api_client: TestClient) -> int:
    r = api_client.post(
        "/api/accounts/",
        json={"name": "Spend Bank", "type": "savings", "account_class": "asset_cash"},
    )
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


def _expense_id(api_client: TestClient) -> int:
    accounts = api_client.get("/api/accounts/")
    assert accounts.status_code == 200, accounts.text
    return int(next(a["id"] for a in accounts.json() if a["name"] == "Uncategorized Expense"))


def _post_bank_expense(api_client: TestClient, *, bank_id: int, amount: int, category: str) -> None:
    expense_id = _expense_id(api_client)
    today = date.today().isoformat()
    r = api_client.post(
        "/api/ledger/transactions",
        json={
            "date": today,
            "pattern": "bank_expense",
            "amount_paise": amount,
            "bank_account_id": bank_id,
            "expense_account_id": expense_id,
            "category": category,
            "merchant": "Test Merchant",
        },
    )
    assert r.status_code == 201, r.text


def test_dashboard_spend_uses_ledger_budget_spend(api_client: TestClient) -> None:
    bank_id = _bank(api_client)
    _post_bank_expense(api_client, bank_id=bank_id, amount=12_500, category="Food")

    summary = api_client.get("/api/dashboard/summary")
    assert summary.status_code == 200, summary.text
    data = summary.json()
    assert data["spent_today_paise"] == 12_500
    assert data["spent_month_paise"] == 12_500
    assert data["spent_by_category_month"].get("Food") == 12_500
    assert data["spent_by_account_month"].get("Spend Bank") == 12_500


def test_budget_vs_actual_uses_ledger_spend(api_client: TestClient) -> None:
    bank_id = _bank(api_client)
    _post_bank_expense(api_client, bank_id=bank_id, amount=8_000, category="Food")

    today = date.today()
    r = api_client.get(f"/api/budget/vs-actual?year={today.year}&month={today.month}")
    assert r.status_code == 200, r.text
    rows = {row["category"]: row for row in r.json()["rows"]}
    assert rows["Food"]["spent_paise"] == 8_000


def test_fy_spending_uses_ledger_spend(api_client: TestClient) -> None:
    bank_id = _bank(api_client)
    _post_bank_expense(api_client, bank_id=bank_id, amount=9_999, category="Travel")

    fy = date_to_fy(date.today())
    r = api_client.get(f"/api/reports/fy-spending?fy={fy}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total_spent_paise"] >= 9_999
    # Current calendar month within FY should include the expense.
    assert any(int(row["spent_paise"]) >= 9_999 for row in data["rows"])
