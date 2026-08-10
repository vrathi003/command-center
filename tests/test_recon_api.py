"""HTTP tests for reconciliation workspaces."""

from __future__ import annotations

from io import BytesIO

from starlette.testclient import TestClient


def _accounts(api_client: TestClient) -> dict[str, int]:
    accounts = (
        ("Bank", "savings", "asset_cash"),
        ("Expense", "expense", "expense"),
    )
    ids: dict[str, int] = {}
    for name, account_type, account_class in accounts:
        response = api_client.post(
            "/api/accounts/",
            json={"name": name, "type": account_type, "account_class": account_class},
        )
        assert response.status_code == 201, response.text
        ids[name] = int(response.json()["id"])
    return ids


def test_import_workspace_suggest_confirm_close_and_reopen(api_client: TestClient) -> None:
    ids = _accounts(api_client)
    ledger = api_client.post(
        "/api/ledger/transactions",
        json={
            "date": "2026-08-10",
            "pattern": "bank_expense",
            "amount_paise": 10_000,
            "bank_account_id": ids["Bank"],
            "expense_account_id": ids["Expense"],
            "category": "Food",
            "payee": "Coffee",
        },
    )
    assert ledger.status_code == 201, ledger.text
    transaction_id = int(ledger.json()["id"])

    created = api_client.post(
        "/api/recon/statements",
        data={
            "account_id": str(ids["Bank"]),
            "period": "2026-08-01/2026-08-31",
            "opening_balance_paise": "0",
            "closing_balance_paise": "-10000",
        },
        files={
            "file": (
                "bank.csv",
                BytesIO(b"date,amount,merchant\n2026-08-10,100,Coffee\n"),
                "text/csv",
            )
        },
    )

    assert created.status_code == 201, created.text
    statement_id = int(created.json()["id"])
    assert created.json()["line_count"] == 1
    assert (
        api_client.get("/api/recon/statements", params={"account_id": ids["Bank"]}).json()[0]["id"]
        == statement_id
    )

    suggestions = api_client.post(f"/api/recon/statements/{statement_id}/suggest")
    assert suggestions.status_code == 200, suggestions.text
    assert suggestions.json()["proposals"][0]["ledger_transaction_id"] == transaction_id

    workspace = api_client.get(f"/api/recon/statements/{statement_id}")
    assert workspace.status_code == 200
    line_id = int(workspace.json()["lines"][0]["id"])
    confirmed = api_client.post(
        f"/api/recon/statements/{statement_id}/lines/{line_id}/confirm",
        json={"ledger_transaction_id": transaction_id},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["line_status"] == "matched"

    closed = api_client.post(f"/api/recon/statements/{statement_id}/soft-close")
    assert closed.status_code == 200, closed.text
    assert closed.json()["can_soft_close"] is True
    assert api_client.post(f"/api/recon/statements/{statement_id}/reopen").status_code == 204
    assert (
        api_client.post(f"/api/recon/statements/{statement_id}/lines/{line_id}/unmatch").status_code
        == 204
    )
    assert (
        api_client.post(
            f"/api/recon/statements/{statement_id}/lines/{line_id}/ignore",
            json={"reason": "intentionally excluded"},
        ).status_code
        == 204
    )


def test_adjustment_requires_ledger_writes(api_client: TestClient) -> None:
    ids = _accounts(api_client)
    created = api_client.post(
        "/api/recon/statements",
        data={
            "account_id": str(ids["Bank"]),
            "period": "2026-08-01/2026-08-31",
            "opening_balance_paise": "0",
            "closing_balance_paise": "-500",
        },
        files={
            "file": (
                "bank.csv",
                BytesIO(b"date,amount,merchant\n2026-08-11,5,Monthly charge\n"),
                "text/csv",
            )
        },
    )
    assert created.status_code == 201, created.text
    statement_id = int(created.json()["id"])

    api_client.app.state.ledger_writes_enabled = False
    disabled = api_client.post(
        f"/api/recon/statements/{statement_id}/adjust",
        json={
            "line_id": 1,
            "counterpart_account_id": ids["Expense"],
            "category": "Bank Charges",
        },
    )
    assert disabled.status_code == 503

    api_client.app.state.ledger_writes_enabled = True
    adjusted = api_client.post(
        f"/api/recon/statements/{statement_id}/adjust",
        json={
            "line_id": 1,
            "counterpart_account_id": ids["Expense"],
            "category": "Bank Charges",
        },
    )
    assert adjusted.status_code == 200, adjusted.text
    assert adjusted.json()["line_id"] == 1
    assert (
        api_client.get(f"/api/recon/statements/{statement_id}").json()["lines"][0]["status"]
        == "matched"
    )
