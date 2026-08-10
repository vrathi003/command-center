"""Credit-card statement application through the double-entry intake flow."""

from __future__ import annotations

import json
import os
import sqlite3

from starlette.testclient import TestClient


def _create_card_and_statement(api_client: TestClient) -> tuple[int, int, int]:
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
    expense_account = api_client.post(
        "/api/accounts/",
        json={"name": "Uncategorized Expense", "type": "expense", "account_class": "expense"},
    )
    assert expense_account.status_code == 201, expense_account.text
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

    conn = sqlite3.connect(os.environ["DB_PATH"])
    statement = conn.execute(
        """
        INSERT INTO credit_card_statements (
            credit_card_id, filename, summary_json, line_items_json, status
        ) VALUES (?, 'statement.csv', ?, ?, 'pending_review')
        """,
        (
            card_id,
            json.dumps({"closing_balance_paise": 10_000}),
            json.dumps(
                [
                    {
                        "date": "2026-08-01",
                        "amount_paise": 10_000,
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
    return card_id, statement_id, cc_account_id


def test_apply_statement_posts_credit_card_spend_through_intake(api_client: TestClient) -> None:
    card_id, statement_id, cc_account_id = _create_card_and_statement(api_client)

    response = api_client.post(f"/api/credit-cards/{card_id}/statements/{statement_id}/apply")

    assert response.status_code == 200, response.text
    assert response.json()["imported_count"] == 1
    conn = sqlite3.connect(os.environ["DB_PATH"])
    candidate = conn.execute(
        """
        SELECT status, source, external_key, suggested_account_id, confidence
        FROM intake_candidates
        """
    ).fetchone()
    ledger_transaction = conn.execute(
        "SELECT source, external_key FROM ledger_transactions"
    ).fetchone()
    legacy_count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()
    conn.close()
    assert candidate == (
        "posted",
        "cc_statement",
        f"cc_statement:{statement_id}:0",
        cc_account_id,
        0.9,
    )
    assert ledger_transaction == (
        "cc_statement",
        f"cc_statement:{statement_id}:0",
    )
    assert legacy_count == (0,)


def test_apply_statement_quarantines_cc_payment_for_bank_confirmation(
    api_client: TestClient,
) -> None:
    card_id, statement_id, _ = _create_card_and_statement(api_client)
    conn = sqlite3.connect(os.environ["DB_PATH"])
    conn.execute(
        """
        UPDATE credit_card_statements
        SET line_items_json = ?
        WHERE id = ?
        """,
        (
            json.dumps(
                [
                    {
                        "date": "2026-08-02",
                        "amount_paise": 10_000,
                        "description": "BBPS Payment received",
                        "transaction_type": "credit",
                    }
                ]
            ),
            statement_id,
        ),
    )
    conn.commit()
    conn.close()

    response = api_client.post(f"/api/credit-cards/{card_id}/statements/{statement_id}/apply")

    assert response.status_code == 200, response.text
    conn = sqlite3.connect(os.environ["DB_PATH"])
    candidate = conn.execute("SELECT status, quarantine_reason FROM intake_candidates").fetchone()
    conn.close()
    assert candidate == ("pending", "cc_payment")


def test_apply_statement_rejects_reapply(api_client: TestClient) -> None:
    card_id, statement_id, _ = _create_card_and_statement(api_client)

    first = api_client.post(f"/api/credit-cards/{card_id}/statements/{statement_id}/apply")
    second = api_client.post(f"/api/credit-cards/{card_id}/statements/{statement_id}/apply")

    assert first.status_code == 200, first.text
    assert second.status_code == 409


def test_apply_statement_requires_linked_account_in_double_entry(
    api_client: TestClient,
) -> None:
    card_id, statement_id, _ = _create_card_and_statement(api_client)
    conn = sqlite3.connect(os.environ["DB_PATH"])
    conn.execute("UPDATE credit_cards SET account_id = NULL WHERE id = ?", (card_id,))
    conn.commit()
    conn.close()

    response = api_client.post(f"/api/credit-cards/{card_id}/statements/{statement_id}/apply")

    assert response.status_code == 422
    assert response.json()["detail"] == "card has no linked account_id"
