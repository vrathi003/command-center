"""Credit-card bill payment through the double-entry ledger."""

from __future__ import annotations

import os
import sqlite3

from starlette.testclient import TestClient


def _create_bank_cc_and_card(api_client: TestClient) -> tuple[int, int, int]:
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

    card = api_client.post(
        "/api/credit-cards/",
        json={
            "name": "Visa",
            "credit_limit_paise": 100_000_00,
            "account_id": cc_account_id,
        },
    )
    assert card.status_code == 201, card.text
    card_id = int(card.json()["id"])

    swipe = api_client.post(
        "/api/ledger/transactions",
        json={
            "pattern": "cc_swipe",
            "date": "2026-08-01",
            "amount_paise": 30_000_00,
            "cc_account_id": cc_account_id,
            "expense_account_id": expense_id,
            "category": "Shopping",
            "source": "dashboard",
        },
    )
    assert swipe.status_code == 201, swipe.text
    return card_id, bank_id, cc_account_id


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


def test_pay_bill_posts_through_ledger_in_double_entry(api_client: TestClient) -> None:
    card_id, bank_id, cc_account_id = _create_bank_cc_and_card(api_client)
    legacy_before = _legacy_transaction_count()

    response = api_client.post(
        f"/api/credit-cards/{card_id}/pay-bill",
        json={
            "from_account_id": bank_id,
            "amount_paise": 10_000_00,
            "date": "2026-08-10",
            "notes": "August bill",
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert "ledger_transaction_id" in body
    assert body.get("transfer_pair_id") is None
    ledger_transaction_id = int(body["ledger_transaction_id"])
    assert ledger_transaction_id > 0

    conn = sqlite3.connect(os.environ["DB_PATH"])
    ledger_row = conn.execute(
        "SELECT source, payee FROM ledger_transactions WHERE id = ?",
        (ledger_transaction_id,),
    ).fetchone()
    conn.close()
    assert ledger_row == ("dashboard", "Visa")

    assert _balance(api_client, bank_id) == -10_000_00
    cc_balance = _balance(api_client, cc_account_id)
    assert cc_balance == -20_000_00
    assert max(0, -cc_balance) == 20_000_00
    assert _legacy_transaction_count() == legacy_before


def test_pay_bill_uses_transfer_pair_in_legacy_engine(api_client: TestClient) -> None:
    card_id, bank_id, cc_account_id = _create_bank_cc_and_card(api_client)
    conn = sqlite3.connect(os.environ["DB_PATH"])
    conn.execute(
        """
        INSERT INTO settings (key, value, updated_at)
        VALUES ('project_config.ledger.engine', 'legacy', datetime('now'))
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """
    )
    conn.commit()
    conn.close()

    response = api_client.post(
        f"/api/credit-cards/{card_id}/pay-bill",
        json={
            "from_account_id": bank_id,
            "amount_paise": 5_000_00,
            "date": "2026-08-11",
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert "ledger_transaction_id" not in body
    assert body["transfer_pair_id"]
    assert body["debit_transaction_id"] > 0
    assert body["credit_transaction_id"] > 0

    conn = sqlite3.connect(os.environ["DB_PATH"])
    ledger_count = conn.execute("SELECT COUNT(*) FROM ledger_transactions").fetchone()
    transfer_count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()
    conn.close()
    assert ledger_count == (1,)  # only the setup swipe
    assert transfer_count == (2,)  # transfer pair for bill pay
