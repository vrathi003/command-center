"""Sync credit_cards.current_balance_paise from ledger after pay_bill and apply."""

from __future__ import annotations

import json
import os
import sqlite3

from starlette.testclient import TestClient


def _cached_balance(card_id: int) -> int | None:
    conn = sqlite3.connect(os.environ["DB_PATH"])
    row = conn.execute(
        "SELECT current_balance_paise FROM credit_cards WHERE id = ?",
        (card_id,),
    ).fetchone()
    conn.close()
    return None if row is None or row[0] is None else int(row[0])


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
            "current_balance_paise": 0,
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


def test_pay_bill_syncs_current_balance_cache(api_client: TestClient) -> None:
    card_id, bank_id, _ = _create_bank_cc_and_card(api_client)
    assert _cached_balance(card_id) == 0

    response = api_client.post(
        f"/api/credit-cards/{card_id}/pay-bill",
        json={
            "from_account_id": bank_id,
            "amount_paise": 10_000_00,
            "date": "2026-08-10",
        },
    )
    assert response.status_code == 201, response.text
    assert _cached_balance(card_id) == 20_000_00


def test_apply_statement_syncs_current_balance_from_ledger_not_summary(
    api_client: TestClient,
) -> None:
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
            "current_balance_paise": 999_999_99,
        },
    )
    assert card.status_code == 201, card.text
    card_id = int(card.json()["id"])

    conn = sqlite3.connect(os.environ["DB_PATH"])
    statement = conn.execute(
        """
        INSERT INTO credit_card_statements (
            credit_card_id, filename, summary_json, line_items_json, status
        ) VALUES (?, 'statement.csv', ?, ?, 'pending_review')
        """,
        (
            card_id,
            json.dumps({"closing_balance_paise": 999_999_99}),
            json.dumps(
                [
                    {
                        "date": "2026-08-01",
                        "amount_paise": 10_000_00,
                        "category": "Food Delivery",
                        "description": "Zomato",
                        "transaction_type": "debit",
                    }
                ]
            ),
        ),
    )
    conn.commit()
    statement_id = int(statement.lastrowid)
    conn.close()

    response = api_client.post(f"/api/credit-cards/{card_id}/statements/{statement_id}/apply")
    assert response.status_code == 200, response.text
    assert _cached_balance(card_id) == 10_000_00
    assert response.json()["updated_balance_paise"] == 10_000_00
