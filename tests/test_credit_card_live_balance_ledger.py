"""Live CC outstanding from liability_cc ledger when double_entry."""

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


def test_live_balance_from_ledger_after_swipe_and_pay_bill(api_client: TestClient) -> None:
    card_id, bank_id, _cc_account_id = _create_bank_cc_and_card(api_client)
    expected_outstanding = 20_000_00

    pay = api_client.post(
        f"/api/credit-cards/{card_id}/pay-bill",
        json={
            "from_account_id": bank_id,
            "amount_paise": 10_000_00,
            "date": "2026-08-10",
        },
    )
    assert pay.status_code == 201, pay.text

    live = api_client.get(f"/api/credit-cards/{card_id}/live-balance")
    assert live.status_code == 200, live.text
    assert live.json()["live_balance_paise"] == expected_outstanding

    detail = api_client.get(f"/api/credit-cards/{card_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["live_balance_paise"] == expected_outstanding

    listing = api_client.get("/api/credit-cards/")
    assert listing.status_code == 200, listing.text
    cards = {c["id"]: c for c in listing.json()}
    assert cards[card_id]["live_balance_paise"] == expected_outstanding


def test_live_balance_uses_legacy_transactions_when_not_double_entry(
    api_client: TestClient,
) -> None:
    card_id, bank_id, cc_account_id = _create_bank_cc_and_card(api_client)
    conn = sqlite3.connect(os.environ["DB_PATH"])
    conn.execute(
        """
        INSERT INTO settings (key, value, updated_at)
        VALUES ('project_config.ledger.engine', 'legacy', datetime('now'))
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """
    )
    conn.execute(
        """
        INSERT INTO transactions (
            date, amount_paise, category, merchant, payment_mode,
            account, source, transaction_type, account_id, is_deleted, updated_at
        ) VALUES ('2026-08-01', ?, 'Shopping', 'Store', 'card', 'Visa', 'bot', 'debit', ?, 0, datetime('now'))
        """,
        (15_000_00, cc_account_id),
    )
    conn.commit()
    conn.close()

    live = api_client.get(f"/api/credit-cards/{card_id}/live-balance")
    assert live.status_code == 200, live.text
    assert live.json()["live_balance_paise"] == 15_000_00
